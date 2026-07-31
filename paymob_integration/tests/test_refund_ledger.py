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

	def test_parent_resend_posts_nothing(self):
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
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(parent.processed, 1)

	def test_void_of_an_authorized_attempt_posts_nothing(self):
		"""The void delta is keyed on `attempt.payment_entry` (processor.py), not on
		`state == "Authorized"` — an authorization never had money posted, so voiding it must
		not fabricate a refunded amount.
		"""
		attempt, request, invoice = given_attempt(state="Authorized", credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		before = payment_entry_count()
		void = given_transaction("Void", "void-authorized", attempt.name, request.name)

		processor.process_transaction(void.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.state, "Voided")
		self.assertEqual(attempt.refunded_amount_cents, 0)

	def test_void_of_a_paid_attempt_with_no_payment_entry_posts_nothing(self):
		"""A `Paid` attempt whose Payment Entry was blocked (e.g. an unresolved amount mismatch,
		ADR-0003) has no money to reverse. Keying the void delta on `attempt.payment_entry` —
		not the `Paid` state alone — is what stops this from fabricating a refunded amount.
		"""
		attempt, request, invoice = given_attempt(state="Paid", credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		self.assertFalse(attempt.payment_entry)
		before = payment_entry_count()
		void = given_transaction("Void", "void-unposted-paid", attempt.name, request.name)

		processor.process_transaction(void.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.state, "Voided")
		self.assertEqual(attempt.refunded_amount_cents, 0)
