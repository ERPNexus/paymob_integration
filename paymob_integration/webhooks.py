"""The app's one `allow_guest=True` endpoint. Paymob's servers have no Frappe session; the
HMAC is the authentication, checked before any document load or database read (ADR-0006).
"""

import frappe

from paymob_integration.paymob import events, hmac_verify, settings

# Reconciliation-relevant fields only — never `billing_data` or similar customer-identity blocks
# Paymob's real payload carries. rules/stored-payment-data.md forbids a second copy of customer
# personal data inside this app; an allowlist (not a denylist) is what stays safe if Paymob adds
# a new field later.
_RAW_PAYLOAD_FIELDS = {
	"id",
	"amount_cents",
	"currency",
	"created_at",
	"success",
	"pending",
	"is_auth",
	"is_capture",
	"is_refunded",
	"is_voided",
	"is_standalone_payment",
	"is_3d_secure",
	"has_parent_transaction",
	"error_occured",
	"integration_id",
	"owner",
}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def processed_callback():
	# frappe.form_dict is built from the JSON body only (make_form_dict, request.is_json) —
	# request.args is never merged in, so the `?hmac=...` query param must be read separately.
	received = frappe.request.args.get("hmac")
	obj = frappe.form_dict.get("obj") or {}

	candidates = settings.enabled_credential_sets()
	credentials = _verifying_credentials(candidates, obj, received)
	if credentials is None:
		frappe.logger("paymob").info(
			f"processed callback refused candidates={len(candidates)} reason=no_matching_secret"
		)
		frappe.local.response["http_status_code"] = 401
		return

	kind = events.classify_event(obj)
	reference, payment_request = _resolve_attempt(obj)

	frappe.logger("paymob").info(
		f"processed callback verified payment_request={payment_request or 'unknown'} "
		f"txn={obj.get('id')} kind={kind} mode={credentials.mode}"
	)

	doc = _store(obj, kind, reference, payment_request)
	if doc:
		# After the commit, not before — a worker must never look for a row the web request
		# has not committed yet. job_id + deduplicate means a redelivery that somehow slips
		# past the primary-key constraint still cannot double-enqueue.
		frappe.enqueue(
			"paymob_integration.paymob.processor.process_transaction",
			queue="short",
			job_id=f"paymob-process-{doc.name}",
			deduplicate=True,
			transaction=doc.name,
		)
	# Stored or a known duplicate — either way ADR-0007 says the response is the same: `200`
	# means "we don't need Paymob to send this again." A persistence failure does not reach
	# here at all; it propagates past this function and becomes a 500 (see _store).
	return "ok"


def _resolve_attempt(obj):
	"""`order.merchant_order_id` is not covered by the processed-callback HMAC — only `order.id`
	is signed (`hmac_verify.PROCESSED_CALLBACK_FIELDS`). Trust the merchant_order_id lookup only
	when the attempt's own frozen `paymob_order_id` matches the signed `order.id`, mirroring
	`www/paymob_result.py::_redirect_is_trusted` — otherwise a genuinely signed callback for one
	order could be misfiled against another attempt's unsigned merchant_order_id.
	"""
	order = obj.get("order") or {}
	reference = order.get("merchant_order_id")
	if not reference:
		return None, None
	attempt = frappe.db.get_value(
		"Paymob Payment Attempt", reference, ["paymob_order_id", "payment_request"], as_dict=True
	)
	if not attempt or not attempt.paymob_order_id or str(attempt.paymob_order_id) != str(order.get("id", "")):
		return None, None
	return reference, attempt.payment_request


def _verifying_credentials(candidates, obj, received):
	"""Trial-verify against every enabled set — no currency filter, which would let a payload
	field choose the secret. A forgery matches none; a genuine callback matches exactly one.
	"""
	for credentials in candidates:
		secret = credentials.get_password("hmac_secret")
		if hmac_verify.verify_processed_callback(obj, received, secret):
			return credentials
	return None


def _store(obj, kind, reference, payment_request):
	"""Insert one Paymob Transaction row and commit before returning, so the `200` this call
	enables means "durably stored" (ADR-0007). `frappe.DuplicateEntryError` — the same delivery
	arriving again — is the only exception caught: it means the row already exists, so there is
	nothing left to do. Anything else propagates, Frappe rolls back and returns a 5xx, and
	Paymob (or the Phase 10 poller) retries.
	"""
	doc = frappe.get_doc(
		{
			"doctype": "Paymob Transaction",
			"paymob_transaction_id": obj.get("id"),
			"event_kind": kind,
			"attempt": reference,
			"payment_request": payment_request,
			"amount_cents": obj.get("amount_cents"),
			"currency": obj.get("currency"),
			"success": obj.get("success"),
			"pending": obj.get("pending"),
			"is_refunded": obj.get("is_refunded"),
			"is_voided": obj.get("is_voided"),
			"refunded_amount_cents": obj.get("refunded_amount_cents"),
			"source": "Webhook",
			"hmac_verified": 1,
			"received_at": frappe.utils.now_datetime(),
			"raw_payload": frappe.as_json(_redact(obj)),
		}
	)
	try:
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		frappe.db.rollback()
		frappe.logger("paymob").info(
			f"processed callback duplicate payment_request={payment_request or 'unknown'} "
			f"txn={obj.get('id')} kind={kind}"
		)
		return None
	frappe.db.commit()
	return doc


def _redact(obj):
	"""Keep only reconciliation-relevant fields, plus `order`/`source_data` trimmed to their
	non-identity sub-fields (`source_data.pan` is Paymob's last-four, not a real PAN — allowed
	under rules/stored-payment-data.md).
	"""
	redacted = {key: obj[key] for key in _RAW_PAYLOAD_FIELDS if key in obj}
	order = obj.get("order")
	if isinstance(order, dict):
		redacted["order"] = {"id": order.get("id"), "merchant_order_id": order.get("merchant_order_id")}
	source_data = obj.get("source_data")
	if isinstance(source_data, dict):
		redacted["source_data"] = {
			"type": source_data.get("type"),
			"sub_type": source_data.get("sub_type"),
			"pan": source_data.get("pan"),
		}
	return redacted
