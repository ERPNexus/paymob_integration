"""Payment Request lifecycle hooks."""

import frappe
from frappe.contacts.doctype.contact.contact import get_default_contact
from frappe.utils import validate_email_address

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
	if not settings.is_enabled(config):
		return
	if not (doc.payment_request_type == "Inward" and doc.reference_doctype and doc.reference_name):
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

	customer_email = _customer_email(doc, source)
	if not customer_email:
		# ERPNext falls back to the reference doc's owner when nothing else is set, which is
		# never the customer. Silence the email rather than mail an internal user a payment link.
		doc.mute_email = 1
		return

	doc.email_to = customer_email
	doc.payment_url = pay_link.build(doc.name)
	if not doc.message:
		doc.message = DEFAULT_MESSAGE


def _customer_email(doc, source):
	"""The customer's own email only — never the invoice owner or another internal fallback.

	`Customer.email_id` is a fetched field pulled from `customer_primary_contact`; it stays blank
	whenever a Customer has contacts but none is flagged primary, even though a usable email
	exists. `get_default_contact` covers that case: primary if set, otherwise any linked contact.
	"""
	email_address = validate_email_address(source.get("contact_email"))
	if email_address:
		return email_address
	if doc.party_type != "Customer" or not doc.party:
		return None

	email_address = validate_email_address(frappe.db.get_value("Customer", doc.party, "email_id"))
	if email_address:
		return email_address

	contact = get_default_contact("Customer", doc.party)
	if contact:
		email_address = validate_email_address(frappe.db.get_value("Contact", contact, "email_id"))
		if email_address:
			return email_address
	return None
