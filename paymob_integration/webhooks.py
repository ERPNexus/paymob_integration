"""The app's one `allow_guest=True` endpoint. Paymob's servers have no Frappe session; the
HMAC is the authentication, checked before any document load or database read (ADR-0006).
"""

import frappe

from paymob_integration.paymob import hmac_verify, settings


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

	frappe.logger("paymob").info(
		f"processed callback verified payment_request={_payment_request_name(obj)} "
		f"txn={obj.get('id')} mode={credentials.mode}"
	)
	# ponytail: acknowledges only. Phase 05 inserts classify -> insert -> commit -> enqueue
	# right here, so the 200 starts meaning "durably stored" instead of just "acknowledged".
	return "ok"


def _verifying_credentials(candidates, obj, received):
	"""Trial-verify against every enabled set — no currency filter, which would let a payload
	field choose the secret. A forgery matches none; a genuine callback matches exactly one.
	"""
	for credentials in candidates:
		secret = credentials.get_password("hmac_secret")
		if hmac_verify.verify_processed_callback(obj, received, secret):
			return credentials
	return None


def _payment_request_name(obj):
	reference = (obj.get("order") or {}).get("merchant_order_id")
	if not reference or "-" not in reference:
		return "unknown"
	return reference.rsplit("-", 1)[0]