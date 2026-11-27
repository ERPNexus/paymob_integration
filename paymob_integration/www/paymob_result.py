"""Customer-facing result page after Paymob checkout. Renders our own stored
Paymob Payment Attempt.state — the redirect's HMAC only decides whether we trust it enough to
show that state, per ADR-0001 and ADR-0011. Trust also requires the signed `order` field to name
*this* attempt's own `paymob_order_id` — otherwise a genuinely signed redirect for one attempt
could be replayed against another attempt's unsigned `merchant_order_id` lookup key.
"""

import frappe
from frappe import _

from paymob_integration import invoice_pay, pay_link, slip
from paymob_integration.paymob import hmac_verify, settings

no_cache = 1

# Raw strings, not `_()`-wrapped: this dict is built once at module import, and `_()` at import
# time would freeze the translation to whichever request's language happened to trigger the
# first import in this worker. Translate at read time in get_context() instead.
MESSAGES = {
	"Pending": "We're confirming your payment.",
	"Paid": "Payment received. Thank you.",
	"Failed": "This payment did not go through. You can try again.",
	"Expired": "This payment link has expired.",
	"Refunded": "This payment has been refunded.",
	"Partially Refunded": "This payment has been partially refunded.",
}


def get_context(context):
	context.no_cache = 1
	context.update(slip.lang_attrs())
	reference = frappe.form_dict.get("merchant_order_id")
	attempt = reference and frappe.db.get_value(
		"Paymob Payment Attempt",
		reference,
		["state", "country", "currency", "payment_request", "mode", "paymob_order_id"],
		as_dict=True,
	)

	if not attempt:
		frappe.logger("paymob").info("result page reason=unknown_reference")
		return _render(context, "Pending")

	trusted = _redirect_is_trusted(attempt)
	if trusted and attempt.state == "Pending":
		# No webhook reaches a site Paymob cannot see; ask Paymob directly while the payer waits.
		try:
			attempt.state = invoice_pay.status_for(attempt.payment_request)["state"]
		except Exception:
			# The payer's money is with Paymob either way; a posting problem is ours to fix, so the
			# page keeps saying "confirming" and the error goes to the log, never to the payer.
			frappe.db.rollback()
			frappe.log_error(title=f"Paymob result inquiry failed payment_request={attempt.payment_request}")
	state = attempt.state if trusted else "Pending"
	if state not in MESSAGES:
		state = "Pending"
	frappe.logger("paymob").info(f"result page shown payment_request={attempt.payment_request} state={state}")
	slip.fill(context, frappe.get_doc("Payment Request", attempt.payment_request))
	if state in ("Failed", "Expired"):
		context.retry_url = pay_link.build(attempt.payment_request)
	return _render(context, state)


def _render(context, state):
	context.state = state
	context.refresh_seconds = 4 if state == "Pending" else None
	context.message = _(MESSAGES.get(state, MESSAGES["Pending"]))
	return context


def _redirect_is_trusted(attempt):
	try:
		# The attempt's own frozen mode, not the site's current mode — an administrator
		# switching Test/Live after checkout started must not change which secret verifies it.
		credentials = settings.get_credential_set(
			attempt.country, attempt.currency, attempt.mode, settings.attempt_company(attempt)
		)
	except frappe.ValidationError as e:
		# get_credential_set throws when Paymob is disabled or the pair is unconfigured —
		# a scoped, narrow catch, not a bare except. Either way we cannot verify, so we
		# cannot trust the URL: fall back to Pending in get_context, never raise a 500.
		frappe.logger("paymob").info(
			f"result page reason=credential_lookup_failed payment_request={attempt.payment_request} error={e}"
		)
		return False

	if not hmac_verify.verify_response_callback(frappe.form_dict, credentials.get_password("hmac_secret")):
		return False

	# The signed `order` field must name this attempt's own order — otherwise a genuinely
	# signed redirect for attempt A, replayed with attempt B's unsigned merchant_order_id,
	# would still pass verification and render B's real state to whoever holds A's link.
	signed_order = frappe.form_dict.get("order") or frappe.form_dict.get("order_id")
	return bool(attempt.paymob_order_id) and str(signed_order) == str(attempt.paymob_order_id)
