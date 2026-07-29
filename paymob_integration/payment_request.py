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


def set_payment_url(doc, method=None):
	"""Give ERPNext's existing Payment Request email a live Paymob link."""
	config = settings.get_settings()
	if not (
		config.enabled
		and config.send_payment_link_email
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

	doc.payment_url = pay_link.build(doc.name)
	if not doc.message:
		doc.message = DEFAULT_MESSAGE
