"""Direct tests for paymob.ledger.post_payment — the single Payment Entry write path
(rules/payments.md rule 1). Called directly here, not through the processor.
"""

from unittest.mock import Mock, patch

import frappe
from erpnext.accounts.doctype.payment_request.payment_request import PaymentRequest

from paymob_integration import api
from paymob_integration.paymob import amounts, ledger
from paymob_integration.tests.helpers import NoCommitIntegrationTestCase, given_submitted_payment_request


def _clearing_account():
	company = frappe.defaults.get_global_default("company")
	return frappe.get_cached_value("Company", company, "default_cash_account")


def _credentials():
	row = Mock()
	row.country = "Egypt"
	row.mode = "Test"
	return row


class TestPostPayment(NoCommitIntegrationTestCase):
	def setUp(self):
		patcher = patch(
			"paymob_integration.paymob.settings.get_credential_set",
			return_value=Mock(payment_account=_clearing_account()),
		)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _given_attempt(self):
		payment_request, invoice = given_submitted_payment_request()
		attempt = api._create_attempt(payment_request, _credentials())
		self.addCleanup(self._cleanup_fixture, attempt.name, payment_request.name, invoice.name)
		return attempt, payment_request, invoice

	def _cleanup_fixture(self, attempt_name, payment_request_name, invoice_name):
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

	def _given_transaction(self, txn_id, attempt, payment_request, amount_cents=27555, currency="EGP"):
		doc = frappe.get_doc(
			{
				"doctype": "Paymob Transaction",
				"paymob_transaction_id": txn_id,
				"event_kind": "Success",
				"attempt": attempt,
				"payment_request": payment_request,
				"amount_cents": amount_cents,
				"currency": currency,
				"success": 1,
				"source": "Webhook",
				"hmac_verified": 1,
				"received_at": frappe.utils.now_datetime(),
				"raw_payload": "{}",
			}
		)
		doc.insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.db.delete("Paymob Transaction", {"paymob_transaction_id": txn_id}))
		return doc

	def test_post_payment_creates_submitted_allocated_payment_entry(self):
		attempt, payment_request, invoice = self._given_attempt()
		before = frappe.db.count("Payment Entry")
		txn = self._given_transaction("900001", attempt.name, payment_request.name)

		payment_entry_name = ledger.post_payment(attempt, txn)

		self.assertEqual(frappe.db.count("Payment Entry"), before + 1)
		payment_entry = frappe.get_doc("Payment Entry", payment_entry_name)
		self.assertEqual(payment_entry.docstatus, 1)
		self.assertEqual(len(payment_entry.references), 1)
		reference = payment_entry.references[0]
		self.assertEqual(reference.reference_name, invoice.name)
		self.assertEqual(reference.payment_request, payment_request.name)
		self.assertEqual(payment_entry.payment_request, payment_request.name)
		self.assertEqual(
			payment_entry.paid_amount, float(amounts.from_minor_units(txn.amount_cents, txn.currency))
		)

		invoice.reload()
		payment_request.reload()
		attempt.reload()
		self.assertEqual(invoice.outstanding_amount, 0)
		self.assertEqual(payment_request.status, "Paid")
		self.assertEqual(attempt.payment_entry, payment_entry_name)

	def test_second_genuine_payment_is_audited_not_posted_again(self):
		attempt, payment_request, _invoice = self._given_attempt()
		before = frappe.db.count("Payment Entry")
		first_txn = self._given_transaction("900002", attempt.name, payment_request.name)
		second_txn = self._given_transaction("900003", attempt.name, payment_request.name)

		first_payment_entry = ledger.post_payment(attempt, first_txn)
		# Mimics what processor.process_transaction does after a successful post — the duplicate
		# lookup only considers Success rows already marked processed.
		first_txn.db_set("processed", 1)
		second_result = ledger.post_payment(attempt, second_txn)

		self.assertIsNotNone(first_payment_entry)
		self.assertIsNone(second_result)
		self.assertEqual(frappe.db.count("Payment Entry"), before + 1)

		attempt.reload()
		self.assertEqual(attempt.needs_human_attention, 1)
		self.assertEqual(attempt.payment_entry, first_payment_entry)

		entries = frappe.get_all(
			"Paymob Audit Entry",
			filters={"paymob_transaction_id": "900003"},
			fields=["event", "needs_action", "description"],
		)
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].event, "Duplicate Payment")
		self.assertEqual(entries[0].needs_action, 1)
		self.assertIn(first_payment_entry, entries[0].description)
		self.assertIn("900002", entries[0].description)

	def test_duplicate_lookup_locks_the_payment_request_not_just_the_attempt(self):
		"""A retry is a new attempt with its own row lock (rules/payments.md) — the duplicate
		guard must serialise on the *Payment Request* they share, or two verified successes for
		two different attempts of the same request could both pass the lookup before either
		Payment Entry exists and both post.
		"""
		attempt, payment_request, _invoice = self._given_attempt()
		txn = self._given_transaction("900005", attempt.name, payment_request.name)

		with patch("frappe.get_doc", wraps=frappe.get_doc) as spied_get_doc:
			ledger.post_payment(attempt, txn)

		locked_payment_request_calls = [
			call
			for call in spied_get_doc.call_args_list
			if call.args[:2] == ("Payment Request", payment_request.name) and call.kwargs.get("for_update")
		]
		self.assertEqual(len(locked_payment_request_calls), 1)

	def test_matches_amount_against_the_account_side_denominated_in_paymob_currency(self):
		"""`paid_amount` lives in the party/company-account currency, `received_amount` in the
		clearing-account currency Paymob actually pays into. A Payment Entry whose party side
		is denominated differently from the transaction must still be compared on its
		Paymob-currency side, not on `paid_amount` unconditionally.
		"""
		attempt, payment_request, _invoice = self._given_attempt()
		txn = self._given_transaction("900006", attempt.name, payment_request.name)
		real_create_payment_entry = PaymentRequest.create_payment_entry

		def _party_side_in_a_different_currency(self, submit=True):
			payment_entry = real_create_payment_entry(self, submit=submit)
			payment_entry.paid_from_account_currency = "SAR"
			payment_entry.paid_amount = 99999  # would be a false mismatch if ever compared to txn.currency
			return payment_entry

		with patch.object(PaymentRequest, "create_payment_entry", _party_side_in_a_different_currency):
			result = ledger.post_payment(attempt, txn)

		self.assertIsNotNone(result)
