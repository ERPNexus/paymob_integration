"""The one function that inserts a Paymob Transaction row — webhook and poller both. Grepping
for "who writes a Paymob Transaction" should return this module alone.
"""

import frappe

from paymob_integration.paymob import events

# Reconciliation-relevant fields only — never `shipping_data`, `order.merchant`, `data.card_num`
# or similar customer/card blocks Paymob's real payload carries. rules/stored-payment-data.md
# forbids a second copy of customer personal data inside this app; an allowlist (not a denylist)
# is what stays safe if Paymob adds a new field later.
#
# The full 179-path payload is catalogued in docs/reference/paymob-payload.md — consult it before
# adding a field here, and add the field there in the same change.
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
	# The refund evidence. `refunded_amount_cents` decides what a refund callback posts, yet it
	# was missing here — stored in its own column and invisible in the payload a human reviews.
	# `is_refund`/`parent_transaction` are what distinguish a child refund from a parent re-send,
	# and `updated_at` dates the re-send (`created_at` still carries the original charge's time).
	"refunded_amount_cents",
	"is_refund",
	"is_void",
	"is_captured",
	"captured_amount",
	"parent_transaction",
	"updated_at",
	"is_live",
}

# Order-level totals worth keeping as evidence. Everything else under `order` — `merchant`,
# `shipping_data`, `data.notification_url` — is identity or config, and stays out.
_RAW_ORDER_FIELDS = (
	"id",
	"merchant_order_id",
	"amount_cents",
	"paid_amount_cents",
	"currency",
	"payment_status",
	"is_returned",
	"is_canceled",
)


def event_key(paymob_transaction_id, event_kind, refunded_amount_cents=None, unsupported_subtype=None):
	"""The dedup key, and the row's own `name` (ADR-0005) — the one place that computes it, so
	`PaymobTransaction.autoname` and anything that needs to find an existing row by the same key
	(e.g. the reconciliation poller recovering a duplicate) can never drift apart.
	"""
	key = f"{paymob_transaction_id}:{event_kind}"
	if event_kind == "Unsupported" and unsupported_subtype:
		key = f"{key}:{unsupported_subtype}"
	if event_kind == "Refund":
		# Paymob resends the same parent transaction id for each cumulative partial refund, with a
		# growing refunded_amount_cents (plans/11-refund-and-void.md).
		key = f"{key}:{refunded_amount_cents or 0}"
	return key


def key_for(obj, kind):
	"""`event_key` for a raw Paymob payload — the one way to find the row `store` refused to
	insert as a duplicate. Callers that rebuild the key themselves drift: they forget
	`unsupported_subtype` and the lookup raises DoesNotExistError inside a money path.
	"""
	return event_key(obj.get("id"), kind, obj.get("refunded_amount_cents"), events.unsupported_subtype(obj))


def verified_charge(attempt_name):
	"""Return the verified, processed Success transaction that charged this attempt."""
	return _verified(attempt_name, ("Success",))


def _verified(attempt_name, kinds):
	for kind in kinds:
		row = frappe.db.get_value(
			"Paymob Transaction",
			{"attempt": attempt_name, "event_kind": kind, "hmac_verified": 1, "processed": 1},
			["paymob_transaction_id", "amount_cents", "currency"],
			as_dict=True,
		)
		if row:
			return row
	return None


def store(obj, kind, reference, payment_request, *, source, hmac_verified):
	"""Insert one Paymob Transaction row and commit before returning, so the caller's
	acknowledgement means "durably stored" (ADR-0007). `frappe.DuplicateEntryError` is the only
	exception caught: the row already exists (a webhook redelivery, or an inquiry finding a
	transaction the callback already delivered), so there is nothing left to do and `None` is
	returned. Anything else propagates — the caller's own error handling decides what happens next.
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
			"has_parent_transaction": obj.get("has_parent_transaction"),
			"refunded_amount_cents": obj.get("refunded_amount_cents"),
			"source": source,
			"hmac_verified": hmac_verified,
			"received_at": frappe.utils.now_datetime(),
			"raw_payload": frappe.as_json(redact(obj)),
		}
	)
	frappe.db.savepoint("paymob_transaction_insert")
	try:
		doc.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		frappe.db.rollback(save_point="paymob_transaction_insert")
		frappe.logger("paymob").info(
			f"{source.lower()} duplicate payment_request={payment_request or 'unknown'} "
			f"txn={obj.get('id')} kind={kind}"
		)
		return None
	frappe.db.commit()
	return doc


def redact(obj):
	"""Keep only reconciliation-relevant fields, plus `order`/`source_data` trimmed to their
	non-identity sub-fields (`source_data.pan` is Paymob's last-four, not a real PAN — allowed
	under rules/stored-payment-data.md).
	"""
	redacted = {key: obj[key] for key in _RAW_PAYLOAD_FIELDS if key in obj}
	order = obj.get("order")
	if isinstance(order, dict):
		redacted["order"] = {key: order[key] for key in _RAW_ORDER_FIELDS if key in order}
	source_data = obj.get("source_data")
	if isinstance(source_data, dict):
		redacted["source_data"] = {
			"type": source_data.get("type"),
			"sub_type": source_data.get("sub_type"),
			"pan": source_data.get("pan"),
		}
	return redacted
