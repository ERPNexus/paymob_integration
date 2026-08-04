"""Verified reversal callbacks create on-account Payment Entries exactly once."""

from unittest.mock import Mock, patch

import frappe

from paymob_integration.paymob import processor
from paymob_integration.tests.helpers import (
	NoCommitIntegrationTestCase,
	cleanup_fixture,
	given_attempt,
	given_transaction,
	payment_entry_count,
)


def _credentials():
	return Mock(country="Egypt", mode="Test")


def _clearing_account():
	company = frappe.defaults.get_global_default("company")
	return frappe.get_cached_value("Company", company, "default_cash_account")


class TestRefundLedger(NoCommitIntegrationTestCase):
	def setUp(self):
		credentials = patch(
			"paymob_integration.paymob.settings.get_credential_set",
			return_value=Mock(payment_account=_clearing_account()),
		)
		credentials.start()
		self.addCleanup(credentials.stop)

	def _paid_attempt(self):
		attempt, request, invoice = given_attempt(credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		success = given_transaction("Success", "refund-success", attempt.name, request.name)
		processor.process_transaction(success.name)
		return attempt, request

	def test_child_refund_posts_its_signed_delta(self):
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		refund = given_transaction(
			"Refund",
			"refund-child",
			attempt.name,
			request.name,
			amount_cents=10000,
			has_parent_transaction=1,
			refunded_amount_cents=27555,
		)

		processor.process_transaction(refund.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(attempt.state, "Partially Refunded")
		self.assertEqual(attempt.refunded_amount_cents, 10000)
		entry = frappe.get_doc(
			"Payment Entry", frappe.get_all("Payment Entry", order_by="creation desc", pluck="name")[0]
		)
		self.assertEqual(entry.payment_type, "Pay")
		self.assertEqual(entry.docstatus, 1)
		self.assertFalse(entry.references)

	def test_the_unsigned_cumulative_field_never_drives_the_amount(self):
		"""`refunded_amount_cents` on the callback is not HMAC-signed (ADR-0017); only the
		child transaction's own signed `amount_cents` may reach the ledger.
		"""
		attempt, request = self._paid_attempt()
		refund = given_transaction(
			"Refund",
			"refund-unsigned-check",
			attempt.name,
			request.name,
			amount_cents=10000,
			has_parent_transaction=1,
			refunded_amount_cents=27555,  # lying: claims the full charge was refunded
		)

		processor.process_transaction(refund.name)

		entry = frappe.get_doc(
			"Payment Entry", frappe.get_all("Payment Entry", order_by="creation desc", pluck="name")[0]
		)
		self.assertEqual(entry.paid_amount, 100)

	def test_parent_resend_ahead_of_posted_refunds_is_audited(self):
		"""Paymob's cumulative total on the parent re-send outrunning what this app has actually
		posted is the #6 symptom — a refund happened at Paymob that never reached the ledger.
		"""
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent",
			attempt.name,
			request.name,
			amount_cents=10000,
			has_parent_transaction=0,
			refunded_amount_cents=10000,
		)

		processor.process_transaction(parent.name)

		parent.reload()
		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(parent.processed, 1)
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(attempt.needs_human_attention, 1)
		audit_entry = frappe.db.get_value(
			"Paymob Audit Entry",
			{"paymob_transaction": parent.name},
			["event", "needs_action", "expected_amount_cents", "received_amount_cents"],
			as_dict=True,
		)
		self.assertEqual(audit_entry.event, "Refund Requires Review")
		self.assertEqual(audit_entry.needs_action, 1)
		# The comparison that triggered the hold, not the re-send's amount_cents (the original charge).
		self.assertEqual(audit_entry.expected_amount_cents, 0)
		self.assertEqual(audit_entry.received_amount_cents, 10000)

	def test_routine_parent_resend_with_matching_total_is_quiet(self):
		"""The parent re-send arrives on every refund, signed or not. When Paymob's cumulative
		total already matches what this app posted, it is routine bookkeeping — no audit entry,
		no flag, just marked processed.
		"""
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-routine",
			attempt.name,
			request.name,
			amount_cents=10000,
			has_parent_transaction=0,
			refunded_amount_cents=0,
		)

		processor.process_transaction(parent.name)

		parent.reload()
		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(parent.processed, 1)
		self.assertEqual(attempt.state, "Paid")
		self.assertFalse(attempt.needs_human_attention)
		self.assertFalse(frappe.db.exists("Paymob Audit Entry", {"paymob_transaction": parent.name}))

	def test_refund_with_no_payment_entry_posts_nothing(self):
		attempt, request, invoice = given_attempt(state="Paid", credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		given_transaction("Success", "refund-unposted-charge", attempt.name, request.name, processed=1)
		before = payment_entry_count()
		refund = given_transaction(
			"Refund",
			"refund-unposted",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=1,
		)

		processor.process_transaction(refund.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.state, "Refunded")
		self.assertFalse(frappe.db.exists("Paymob Audit Entry", {"paymob_transaction": refund.name}))
