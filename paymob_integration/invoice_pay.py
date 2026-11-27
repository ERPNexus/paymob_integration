"""Pay one Sales Invoice by link: the shared server half of every "pay by card or wallet" button.

Callers (a rep app, a merchant app, a portal) check that the user may act on the invoice first;
this module only knows invoices and Payment Requests. Nothing here marks anything paid: that stays
with the signed callback or the reconciliation inquiry (rules/payments.md rule 1).
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, now_datetime

from paymob_integration import pay_link, tasks
from paymob_integration.paymob import client, settings

OPEN_STATES = ("Initiated", "Requested", "Partially Paid", "Payment Ordered")
# ponytail: one inquiry per attempt every few seconds is plenty for a screen that polls.
INQUIRY_GAP_SECONDS = 5


def enabled():
	return settings.is_enabled()


def link_for(invoice: str) -> dict:
	"""The open Payment Request for the invoice's whole outstanding amount, created if missing.

	A request for a different amount (a cash collection landed since) is cancelled and replaced:
	a link must never ask for more than the shop still owes.
	"""
	settings.is_enabled(throw=True)
	si = frappe.get_doc("Sales Invoice", invoice)
	outstanding = flt(si.outstanding_amount, 2)
	if si.docstatus != 1 or si.is_return or outstanding <= 0:
		frappe.throw(_("This invoice has nothing left to pay."))

	for row in _open_requests(invoice):
		# A live checkout keeps its request even at an old amount: someone may be on the card page
		# right now, and a second request beside it is how an invoice gets paid twice.
		if flt(row.grand_total, 2) == outstanding or _has_live_payment(row.name):
			return _describe(frappe.get_doc("Payment Request", row.name), si)
		cancelled = frappe.get_doc("Payment Request", row.name)
		cancelled.flags.ignore_permissions = True
		cancelled.cancel()

	request = frappe.get_doc(
		{
			"doctype": "Payment Request",
			"payment_request_type": "Inward",
			"transaction_date": frappe.utils.nowdate(),
			"reference_doctype": "Sales Invoice",
			"reference_name": si.name,
			"party_type": "Customer",
			"party": si.customer,
			"party_name": si.customer_name,
			"company": si.company,
			"currency": si.currency,
			"grand_total": outstanding,
			"payment_channel": "Email",
			"mute_email": 1,
			"email_to": si.contact_email or "",
			"subject": _("Payment Request for {0}").format(si.name),
			"message": _("Pay invoice {0}").format(si.name),
		}
	)
	request.flags.ignore_permissions = True
	request.insert()
	request.submit()
	return _describe(request, si)


def status_for(payment_request: str) -> dict:
	"""Where one payment stands, asking Paymob first when a checkout is waiting on it."""
	attempt = frappe.db.get_value(
		"Paymob Payment Attempt",
		{"payment_request": payment_request},
		["name", "state", "last_polled_at"],
		as_dict=True,
		order_by="creation desc",
	)
	if attempt and attempt.state == "Pending" and _due_for_inquiry(attempt.last_polled_at):
		try:
			tasks._reconcile(attempt.name)
			frappe.db.commit()
		except client.PaymobError:
			pass  # still Pending; the next poll asks again
	request = frappe.get_doc("Payment Request", payment_request)
	si = frappe.get_doc(request.reference_doctype, request.reference_name)
	return _describe(request, si)


def _describe(request, si) -> dict:
	attempt_state = frappe.db.get_value(
		"Paymob Payment Attempt",
		{"payment_request": request.name},
		"state",
		order_by="creation desc",
	)
	paid = request.status == "Paid" or attempt_state in ("Paid", "Partially Refunded", "Refunded")
	return {
		"payment_request": request.name,
		"invoice": si.name,
		"customer": si.customer,
		"customer_name": si.customer_name,
		"company": si.company,
		"amount": flt(request.grand_total, 2),
		"currency": request.currency,
		"url": pay_link.build(request.name),
		# Open (link not used yet), Pending (on the card page), Paid, Failed, Expired, Cancelled.
		"state": "Paid" if paid else ("Cancelled" if request.docstatus == 2 else (attempt_state or "Open")),
	}


def _open_requests(invoice):
	return frappe.get_all(
		"Payment Request",
		filters={
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice,
			"docstatus": 1,
			"status": ["in", OPEN_STATES],
		},
		fields=["name", "grand_total"],
		order_by="creation desc",
	)


def _has_live_payment(payment_request):
	return frappe.db.exists(
		"Paymob Payment Attempt",
		{"payment_request": payment_request, "state": ["in", ("Pending", "Paid")], "expires_at": [">", now_datetime()]},
	)


def _due_for_inquiry(last_polled_at):
	return not last_polled_at or last_polled_at < add_to_date(now_datetime(), seconds=-INQUIRY_GAP_SECONDS)
