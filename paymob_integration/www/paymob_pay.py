"""Signed payer link that redirects to a current Paymob checkout."""

import frappe
from frappe import _
from frappe.utils.verified_command import verify_request

from paymob_integration import api

no_cache = 1


def get_context(context):
	context.no_cache = 1
	if not verify_request():
		return context

	request_name = frappe.form_dict.get("ref")
	if not request_name:
		return _render_error(context)

	user = frappe.session.user
	try:
		request = frappe.get_doc("Payment Request", request_name)
		frappe.set_user("Administrator")
		checkout = api._checkout(request, reuse_pending=True)
	except frappe.ValidationError:
		frappe.log_error(title=f"Paymob payment link failed payment_request={request_name}")
		return _render_error(context)
	finally:
		frappe.set_user(user)

	frappe.local.flags.redirect_location = checkout["checkout_url"]
	raise frappe.Redirect


def _render_error(context):
	context.message = _("We could not start your payment. Please contact the merchant.")
	return context
