"""The Desk 'Process' button (ADR-0013): a manual rescue for a row stuck at `processed = 0`,
delegating to the same idempotent consumer the webhook enqueues.
"""

from unittest.mock import Mock, patch

import frappe

from paymob_integration import api
from paymob_integration.paymob_integration.doctype.paymob_transaction.paymob_transaction import process
from paymob_integration.tests.helpers import NoCommitIntegrationTestCase, given_submitted_payment_request


def _credentials():
	row = Mock()
	row.country = "Egypt"
	row.mode = "Test"
	return row


def _clearing_account():
	company = frappe.defaults.get_global_default("company")
	return frappe.get_cached_value("Company", company, "default_cash_account")


class TestProcessButton(NoCommitIntegrationTestCase):
	def setUp(self):
		patcher = patch(
			"paymob_integration.paymob.settings.get_credential_set",
			return_value=Mock(payment_account=_clearing_account()),
		)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _given_stuck_transaction(self):
		payment_request, invoice = given_submitted_payment_request()
		attempt = api._create_attempt(payment_request, _credentials())
		txn = frappe.get_doc(
			{
				"doctype": "Paymob Transaction",
				"paymob_transaction_id": "600001",
				"event_kind": "Success",
				"attempt": attempt.name,
				"payment_request": payment_request.name,
				"amount_cents": 27555,
				"currency": "EGP",
				"success": 1,
				"source": "Webhook",
				"hmac_verified": 1,
				"received_at": frappe.utils.now_datetime(),
				"raw_payload": "{}",
			}
		)
		txn.insert(ignore_permissions=True)
		self.addCleanup(self._cleanup_fixture, attempt.name, payment_request.name, invoice.name)
		return attempt, txn

	def _cleanup_fixture(self, attempt_name, payment_request_name, invoice_name):
		for payment_entry in frappe.get_all(
			"Payment Entry Reference", {"payment_request": payment_request_name}, pluck="parent"
		):
			pe = frappe.get_doc("Payment Entry", payment_entry)
			if pe.docstatus == 1:
				pe.cancel()
			frappe.delete_doc("Payment Entry", payment_entry, force=True, ignore_permissions=True)
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

	def test_guest_cannot_press_the_button(self):
		_, txn = self._given_stuck_transaction()
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")

		self.assertRaises(frappe.PermissionError, process, txn.name)

	def test_process_button_drives_the_stuck_row_to_paid(self):
		attempt, txn = self._given_stuck_transaction()

		process(txn.name)

		attempt.reload()
		txn.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(txn.processed, 1)
		self.assertTrue(attempt.payment_entry)

	def test_process_leaves_the_session_intact(self):
		"""Regression for #8: the button used to run privileged work through a bare `set_user`
		pair, whose `finally` stamps `session.sid` to the *username* and empties `session.data`
		on the way back out — corrupting the real session so the button's own follow-up request
		(`frm.reload_doc()`) got logged out.
		"""
		_, txn = self._given_stuck_transaction()
		original_sid = frappe.local.session.sid
		original_data = frappe.local.session.data
		self.addCleanup(setattr, frappe.local.session, "sid", original_sid)
		self.addCleanup(setattr, frappe.local.session, "data", original_data)
		sentinel_data = frappe._dict({"csrf_token": "sentinel-token"})
		frappe.local.session.sid = "sentinel-sid-issue-8"
		frappe.local.session.data = sentinel_data

		process(txn.name)

		self.assertEqual(frappe.local.session.sid, "sentinel-sid-issue-8")
		self.assertIs(frappe.local.session.data, sentinel_data)
