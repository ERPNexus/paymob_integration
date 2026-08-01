"""Payment Request lifecycle hooks."""

import frappe

from paymob_integration import api, email, pay_link
from paymob_integration.paymob import settings

DEFAULT_MESSAGE = email.render(
	"{{ _('Pay with Paymob') }}",
	"{{ _('Payment link ready') }}",
	email.INFO,
	"<p>{{ _('Please use the link below to pay this request.') }}</p>",
	"doc.company",
	"{{ _('Make Payment') }}",
	"{{ payment_url }}",
)


def prepare_payment_email(doc, method=None):
	"""Own the submit-time email whenever Paymob owns the payment: give it a live Paymob link,
	or mute it.

	Runs on `validate`, not `before_submit`. ERPNext's own `before_submit` builds and enqueues
	that email inside its method body, and Frappe always runs a DocType's own controller method
	ahead of an app's `doc_events` handler for the same event — so anything set in a
	`before_submit` hook lands after the mail has already gone out (ADR-0024).
	"""
	config = settings.get_settings()
	if not (
		config.enabled
		and doc.payment_request_type == "Inward"
		and doc.reference_doctype
		and doc.reference_name
	):
		return

	try:
		source = frappe.get_doc(doc.reference_doctype, doc.reference_name)
		settings.get_credential_set(api._merchant_country(doc, source), doc.currency)
	except frappe.ValidationError:
		return

	if not config.send_payment_link_email:
		# Never let ERPNext's generic "Make Payment" email go out with no working Paymob link.
		doc.mute_email = 1
		return

	doc.payment_url = pay_link.build(doc.name)
	if not doc.message:
		doc.message = DEFAULT_MESSAGE
