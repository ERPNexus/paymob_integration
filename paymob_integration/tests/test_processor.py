"""Integration paths for paymob.processor.process_transaction. A `Success` on a `Pending`
attempt now posts a Payment Entry through `paymob.ledger.post_payment` — every other scenario
still counts zero.
"""

from unittest.mock import Mock, patch

import frappe

from paymob_integration import api
from paymob_integration.paymob import processor
from paymob_integration.paymob_integration.report.paymob_open_audit_entries.paymob_open_audit_entries import (
	execute,
)
from paymob_integration.tests.helpers import (
	NoCommitIntegrationTestCase,
	cleanup_fixture,
	given_attempt,
	given_submitted_payment_request,
	given_transaction,
	payment_entry_count,
)


def _credentials():
	row = Mock()
	row.country = "Egypt"
	row.mode = "Test"
	return row


def _clearing_account():
	company = frappe.defaults.get_global_default("company")
	return frappe.get_cached_value("Company", company, "default_cash_account")


def _forget_transaction(txn_id):
	"""Clean up a bare transaction fixture with no attempt or Payment Request."""
	frappe.db.delete("Paymob Transaction", {"paymob_transaction_id": txn_id})
	frappe.db.delete("Paymob Audit Entry", {"paymob_transaction_id": txn_id})


class TestProcessTransaction(NoCommitIntegrationTestCase):
	def setUp(self):
		patcher = patch(
			"paymob_integration.paymob.settings.get_credential_set",
			return_value=Mock(payment_account=_clearing_account()),
		)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _given_attempt(self, state="Pending"):
		attempt, payment_request, invoice = given_attempt(state, credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, payment_request.name, invoice.name)
		return attempt, payment_request, invoice

	def _cleanup_fixture(self, attempt_name, payment_request_name, invoice_name):
		cleanup_fixture(attempt_name, payment_request_name, invoice_name)

	def _given_transaction(self, event_kind, txn_id, **kwargs):
		doc = given_transaction(event_kind, txn_id, **kwargs)
		self.addCleanup(_forget_transaction, txn_id)
		return doc

	def _payment_entry_count(self):
		return payment_entry_count()

	def test_success_on_pending_attempt_moves_to_paid(self):
		attempt, payment_request, invoice = self._given_attempt()
		before = self._payment_entry_count()

		txn = self._given_transaction(
			"Success", "700001", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(txn.name)

		attempt.reload()
		txn.reload()
		invoice.reload()
		payment_request.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(txn.processed, 1)
		self.assertEqual(self._payment_entry_count(), before + 1)
		self.assertTrue(attempt.payment_entry)
		payment_entry = frappe.get_doc("Payment Entry", attempt.payment_entry)
		self.assertEqual(payment_entry.docstatus, 1)
		reference = payment_entry.references[0]
		self.assertEqual(reference.reference_name, invoice.name)
		self.assertEqual(reference.payment_request, payment_request.name)
		self.assertEqual(invoice.outstanding_amount, 0)
		self.assertEqual(payment_request.status, "Paid")

	def test_success_posts_payment_entry_when_enqueued_as_guest(self):
		"""The processed callback is `allow_guest=True` (ADR-0006); `frappe.enqueue` inherits
		that request's user, so the real job always starts as Guest, not Administrator. ADR-0013.
		"""
		attempt, payment_request, invoice = self._given_attempt()
		txn = self._given_transaction(
			"Success", "700020", attempt=attempt.name, payment_request=payment_request.name
		)
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")

		processor.process_transaction(txn.name)

		self.assertEqual(frappe.session.user, "Guest")
		attempt.reload()
		invoice.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertTrue(attempt.payment_entry)
		self.assertEqual(invoice.outstanding_amount, 0)

	def test_second_genuine_success_is_audited_as_duplicate_payment(self):
		"""rules/testing.md: 'Two genuine payments for one Payment Request: one Payment Entry,
		one audit record.'
		"""
		attempt, payment_request, invoice = self._given_attempt()
		before = self._payment_entry_count()

		first = self._given_transaction(
			"Success", "700012", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(first.name)
		second = self._given_transaction(
			"Success", "700013", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(second.name)

		attempt.reload()
		second.reload()
		invoice.reload()
		self.assertEqual(self._payment_entry_count(), before + 1)
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(attempt.needs_human_attention, 1)
		self.assertEqual(second.processed, 1)
		self.assertEqual(invoice.outstanding_amount, 0)

		entries = frappe.get_all(
			"Paymob Audit Entry",
			filters={"paymob_transaction_id": "700013"},
			fields=["event", "needs_action", "paymob_transaction"],
		)
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].event, "Duplicate Payment")
		self.assertEqual(entries[0].needs_action, 1)
		self.assertEqual(entries[0].paymob_transaction, second.name)

	def test_success_after_decline_posts_once_without_audit(self):
		attempt, payment_request, invoice = self._given_attempt()
		before = self._payment_entry_count()

		decline = self._given_transaction(
			"Decline", "700002", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(decline.name)

		attempt.reload()
		self.assertEqual(attempt.state, "Failed")
		self.assertEqual(self._payment_entry_count(), before)

		success = self._given_transaction(
			"Success", "700003", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(success.name)
		invoice.reload()
		payment_request.reload()
		attempt.reload()
		success.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(success.processed, 1)
		self.assertEqual(self._payment_entry_count(), before + 1)
		self.assertTrue(attempt.payment_entry)
		payment_entry = frappe.get_doc("Payment Entry", attempt.payment_entry)
		self.assertEqual(payment_entry.docstatus, 1)
		self.assertEqual(payment_entry.references[0].reference_name, invoice.name)
		self.assertEqual(payment_entry.references[0].payment_request, payment_request.name)
		self.assertEqual(invoice.outstanding_amount, 0)
		self.assertEqual(payment_request.status, "Paid")
		self.assertEqual(attempt.needs_human_attention, 0)
		self.assertFalse(
			frappe.db.exists("Paymob Audit Entry", {"paymob_transaction_id": success.paymob_transaction_id})
		)

		processor.process_transaction(success.name)
		self.assertEqual(self._payment_entry_count(), before + 1)

	def test_decline_on_paid_attempt_is_refused_and_audited(self):
		attempt, payment_request, _invoice = self._given_attempt(state="Paid")

		txn = self._given_transaction(
			"Decline", "700004", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(txn.name)

		attempt.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"paymob_transaction_id": "700004"}), 1)

	def test_decline_on_already_failed_attempt_is_a_noop(self):
		attempt, payment_request, _invoice = self._given_attempt(state="Failed")

		txn = self._given_transaction(
			"Decline", "700005", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(txn.name)

		txn.reload()
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"paymob_transaction_id": "700005"}), 0)
		self.assertEqual(txn.processed, 1)

	def test_unsupported_event_is_stored_audited_and_never_posts(self):
		attempt, payment_request, _invoice = self._given_attempt()
		before = self._payment_entry_count()
		txn = self._given_transaction(
			"Unsupported", "700006", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(txn.name)

		attempt.reload()
		txn.reload()
		self.assertEqual(attempt.state, "Pending")
		self.assertEqual(attempt.needs_human_attention, 1)
		self.assertEqual(txn.processed, 1)
		self.assertEqual(self._payment_entry_count(), before)
		self.assertTrue(
			frappe.db.exists(
				"Paymob Audit Entry",
				{"paymob_transaction_id": "700006", "event": "Unsupported Paymob Event"},
			)
		)

	def test_pending_kind_is_consumed_without_state_change(self):
		attempt, payment_request, _invoice = self._given_attempt()
		txn = self._given_transaction(
			"Pending", "700007", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(txn.name)

		txn.reload()
		attempt.reload()
		self.assertEqual(txn.processed, 1)
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"paymob_transaction_id": "700007"}), 0)
		self.assertEqual(attempt.state, "Pending")

	def test_unattributed_success_is_audited(self):
		txn = self._given_transaction("Success", "700008")
		processor.process_transaction(txn.name)

		txn.reload()
		entries = frappe.get_all(
			"Paymob Audit Entry",
			filters={"paymob_transaction_id": "700008"},
			fields=["event", "needs_action"],
		)
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].event, "Unattributed Payment")
		self.assertEqual(entries[0].needs_action, 1)
		self.assertEqual(txn.processed, 1)

	def test_unattributed_decline_is_not_audited(self):
		txn = self._given_transaction("Decline", "700009")
		processor.process_transaction(txn.name)

		txn.reload()
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"paymob_transaction_id": "700009"}), 0)
		self.assertEqual(txn.processed, 1)

	def test_reprocessing_a_processed_row_is_a_noop(self):
		attempt, payment_request, _invoice = self._given_attempt(state="Failed")
		txn = self._given_transaction(
			"Success", "700010", attempt=attempt.name, payment_request=payment_request.name
		)

		processor.process_transaction(txn.name)
		processor.process_transaction(txn.name)

		attempt.reload()
		self.assertEqual(attempt.state, "Failed")
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"paymob_transaction_id": "700010"}), 1)

	def test_audit_entry_is_immutable(self):
		attempt, payment_request, _invoice = self._given_attempt(state="Failed")
		txn = self._given_transaction(
			"Success", "700011", attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(txn.name)

		entry = frappe.get_doc(
			"Paymob Audit Entry",
			frappe.db.get_value("Paymob Audit Entry", {"paymob_transaction_id": "700011"}),
		)
		entry.description = "tampered"
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			entry.save()

	def test_open_audit_entries_report_excludes_superseded_rows(self):
		_attempt, payment_request, _invoice = self._given_attempt(state="Failed")

		first = self._make_audit_entry(payment_request.name, "800001", needs_action=1)
		second = self._make_audit_entry(payment_request.name, "800002", needs_action=1)
		self._make_audit_entry(payment_request.name, "800003", needs_action=0, supersedes=first.name)

		_columns, rows = execute()
		names = {row["name"] for row in rows}
		self.assertIn(second.name, names)
		self.assertNotIn(first.name, names)

	def _make_audit_entry(self, payment_request, txn_id, needs_action, supersedes=None):
		entry = frappe.get_doc(
			{
				"doctype": "Paymob Audit Entry",
				"payment_request": payment_request,
				"paymob_transaction_id": txn_id,
				"event": "Illegal Transition",
				"description": "test fixture",
				"actor": "test",
				"occurred_at": frappe.utils.now_datetime(),
				"needs_action": needs_action,
				"supersedes": supersedes,
			}
		)
		entry.insert(ignore_permissions=True)
		entry.submit()
		self.addCleanup(lambda: frappe.db.delete("Paymob Audit Entry", {"paymob_transaction_id": txn_id}))
		return entry


class TestAmountMismatch(NoCommitIntegrationTestCase):
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

	def _given_transaction(self, txn_id, amount_cents, currency="EGP", attempt=None, payment_request=None):
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
		self.addCleanup(_forget_transaction, txn_id)
		return doc

	def test_underpayment_is_held_for_review(self):
		attempt, payment_request, invoice = self._given_attempt()
		before = frappe.db.count("Payment Entry")
		txn = self._given_transaction(
			"800101", 27554, attempt=attempt.name, payment_request=payment_request.name
		)

		processor.process_transaction(txn.name)

		attempt.reload()
		invoice.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(attempt.needs_human_attention, 1)
		entries = frappe.get_all(
			"Paymob Audit Entry",
			filters={"paymob_transaction_id": "800101"},
			fields=["event", "expected_amount_cents", "received_amount_cents"],
		)
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].event, "Amount Mismatch")
		self.assertEqual(entries[0].expected_amount_cents, 27555)
		self.assertEqual(entries[0].received_amount_cents, 27554)
		self.assertEqual(frappe.db.count("Payment Entry"), before)
		self.assertNotEqual(invoice.status, "Paid")

	def test_overpayment_is_held_for_review(self):
		attempt, payment_request, _invoice = self._given_attempt()
		txn = self._given_transaction(
			"800102", 27556, attempt=attempt.name, payment_request=payment_request.name
		)

		processor.process_transaction(txn.name)

		attempt.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(attempt.needs_human_attention, 1)
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"paymob_transaction_id": "800102"}), 1)

	def test_currency_mismatch_is_held_for_review(self):
		attempt, payment_request, _invoice = self._given_attempt()
		txn = self._given_transaction(
			"800103", 27555, currency="SAR", attempt=attempt.name, payment_request=payment_request.name
		)

		processor.process_transaction(txn.name)

		attempt.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(attempt.needs_human_attention, 1)
		entries = frappe.get_all(
			"Paymob Audit Entry",
			filters={"paymob_transaction_id": "800103"},
			fields=["expected_currency", "received_currency"],
		)
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0].expected_currency, "EGP")
		self.assertEqual(entries[0].received_currency, "SAR")

	def test_exact_match_raises_no_flag_and_no_audit_entry(self):
		attempt, payment_request, _invoice = self._given_attempt()
		before = frappe.db.count("Payment Entry")
		txn = self._given_transaction(
			"800104", 27555, attempt=attempt.name, payment_request=payment_request.name
		)

		processor.process_transaction(txn.name)

		attempt.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(attempt.needs_human_attention, 0)
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"paymob_transaction_id": "800104"}), 0)
		self.assertEqual(frappe.db.count("Payment Entry"), before + 1)
		self.assertTrue(attempt.payment_entry)

	def test_mismatch_appears_in_open_audit_entries_report(self):
		attempt, payment_request, _invoice = self._given_attempt()
		txn = self._given_transaction(
			"800105", 27554, attempt=attempt.name, payment_request=payment_request.name
		)
		processor.process_transaction(txn.name)

		_columns, rows = execute()
		self.assertIn("800105", {row["paymob_transaction_id"] for row in rows})
