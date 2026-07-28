"""Build the ERPNext documents checkout integration tests act on."""

from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from paymob_integration import api


class NoCommitIntegrationTestCase(IntegrationTestCase):
	"""Keep each integration-test class inside Frappe's rollback transaction."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		commit = patch.object(frappe.db, "commit", return_value=None)
		commit.start()
		cls.addClassCleanup(commit.stop)


def mock_credentials():
	row = Mock()
	row.country = "Egypt"
	row.mode = "Test"
	return row


def given_attempt(state="Pending", credentials=None):
	"""A Paymob Payment Attempt against a fresh submitted Payment Request. Caller registers
	`cleanup_fixture` via `addCleanup` — this function does not know about the test case.
	"""
	payment_request, invoice = given_submitted_payment_request()
	attempt = api._create_attempt(payment_request, credentials or mock_credentials())
	if state != "Pending":
		attempt.state = state
		attempt.save(ignore_permissions=True)
	return attempt, payment_request, invoice


def cleanup_fixture(attempt_name, payment_request_name, invoice_name):
	"""Cancel/delete the Payment Entry first — it blocks deleting both the Payment Request and
	the Sales Invoice while submitted.
	"""
	for payment_entry in frappe.get_all(
		"Payment Entry Reference", {"payment_request": payment_request_name}, pluck="parent"
	):
		pe = frappe.get_doc("Payment Entry", payment_entry)
		if pe.docstatus == 1:
			pe.cancel()
		frappe.delete_doc("Payment Entry", payment_entry, force=True, ignore_permissions=True)
	frappe.db.delete("Paymob Audit Entry", {"payment_request": payment_request_name})
	frappe.db.delete("Paymob Transaction", {"payment_request": payment_request_name})
	frappe.delete_doc("Paymob Payment Attempt", attempt_name, force=True, ignore_permissions=True)
	payment_request = frappe.get_doc("Payment Request", payment_request_name)
	if payment_request.docstatus == 1:
		payment_request.cancel()
	frappe.delete_doc("Payment Request", payment_request_name, force=True, ignore_permissions=True)
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	if invoice.docstatus == 1:
		invoice.cancel()
	frappe.delete_doc("Sales Invoice", invoice_name, force=True, ignore_permissions=True)


def given_transaction(
	event_kind,
	txn_id,
	attempt=None,
	payment_request=None,
	amount_cents=27555,
	currency="EGP",
	**overrides,
):
	doc = frappe.get_doc(
		{
			"doctype": "Paymob Transaction",
			"paymob_transaction_id": txn_id,
			"event_kind": event_kind,
			"attempt": attempt,
			"payment_request": payment_request,
			"amount_cents": amount_cents,
			"currency": currency,
			"success": event_kind == "Success",
			"pending": event_kind == "Pending",
			"is_refunded": event_kind == "Refund",
			"is_voided": event_kind == "Void",
			"source": "Webhook",
			"hmac_verified": 1,
			"received_at": frappe.utils.now_datetime(),
			"raw_payload": "{}",
			**overrides,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def payment_entry_count():
	return frappe.db.count("Payment Entry")


def given_user_with_role(role):
	"""A fresh user holding exactly one role, for permission-gate tests."""
	email = f"paymob-{frappe.scrub(role)}@example.test"
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
	return email


def given_submitted_payment_request(grand_total="275.55", currency="EGP"):
	"""Create a submitted invoice and its matching incoming Payment Request."""
	invoice = given_submitted_sales_invoice(grand_total, currency)
	payment_request = frappe.get_doc(
		{
			"doctype": "Payment Request",
			"payment_request_type": "Inward",
			"transaction_date": frappe.utils.nowdate(),
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice.name,
			"party_type": "Customer",
			"party": invoice.customer,
			"company": invoice.company,
			"currency": currency,
			"grand_total": grand_total,
			"payment_channel": "Email",
			"mute_email": 1,
			"email_to": "customer@example.test",
			"subject": "Payment Request",
			"message": "Please pay",
		}
	)
	payment_request.insert(ignore_permissions=True)
	payment_request.submit()
	return payment_request, invoice


def given_submitted_sales_invoice(grand_total="275.55", currency="EGP"):
	"""Create one non-stock invoice line at exactly the requested amount.

	`disable_rounded_total` avoids a mismatch on sites whose Currency master rounds to a whole
	unit (`smallest_currency_fraction_value = 0`) — without it, `outstanding_amount` silently
	differs from `grand_total`, which any test asserting the ledger down to the cent depends on.
	"""
	company = frappe.defaults.get_global_default("company")
	customer = _ensure_customer(currency)
	item = _ensure_item()
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": customer,
			"currency": currency,
			"conversion_rate": 1,
			"disable_rounded_total": 1,
			"due_date": frappe.utils.nowdate(),
			"items": [{"item_code": item, "qty": 1, "rate": grand_total}],
		}
	)
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	return invoice


def _ensure_customer(currency):
	name = "Paymob Test Customer"
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
				"default_currency": currency,
			}
		).insert(ignore_permissions=True)
	return name


def _ensure_item():
	code = "PAYMOB-TEST-ITEM"
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
	return code
