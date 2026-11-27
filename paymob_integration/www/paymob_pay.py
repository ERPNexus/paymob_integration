"""Signed payer link: shows what is being paid, then hands off to a current Paymob checkout."""

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.verified_command import verify_request

from paymob_integration import api, invoice_pay, slip
from paymob_integration.paymob import session

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.update(slip.lang_attrs())
	if not verify_request():
		return context

	request_name = frappe.form_dict.get("ref")
	if not request_name or not frappe.db.exists("Payment Request", request_name):
		return slip.error(context, _("This payment link is not valid. Ask the seller for a new one."))

	request = frappe.get_doc("Payment Request", request_name)
	slip.fill(context, request)
	if request.status == "Paid":
		context.state = "Paid"
		return context

	source = frappe.get_doc(request.reference_doctype, request.reference_name)
	# The request was priced when the link was made; a cash collection since then lowers what is
	# owed, and a card page must never ask for more than that.
	if request.docstatus != 1 or invoice_pay.owed(source) < flt(request.grand_total, 2):
		return slip.error(context, _("This link is out of date. Ask {0} for a new one.").format(context.company_name))

	try:
		with session.as_administrator():
			checkout = api._checkout(request, reuse_pending=True)
	except frappe.ValidationError:
		frappe.log_error(title=f"Paymob payment link failed payment_request={request_name}")
		return slip.error(
			context,
			_("We could not start the payment. Try again in a minute, or contact {0}.").format(context.company_name),
		)

	context.state = "Payable"
	context.checkout_url = checkout["checkout_url"]
	return context
