"""Outbound refund requests: the lock, the marker, the permission gate, and the amount
check. `api.request_refund` never writes the ledger — only the verified
callback processed by `paymob.ledger.post_refund` does that (see test_refund_ledger.py).
"""

from unittest.mock import Mock, patch

import frappe

from paymob_integration import api
from paymob_integration.paymob import client
from paymob_integration.tests.helpers import (
	NoCommitIntegrationTestCase,
	cleanup_fixture,
	given_attempt,
	given_transaction,
	given_user_with_role,
	payment_entry_count,
)


def _credentials():
	return Mock(country="Egypt", mode="Test", payment_account="Cash - PT")


class _RefundTestCase(NoCommitIntegrationTestCase):
	def setUp(self):
		credentials = patch(
			"paymob_integration.paymob.settings.get_credential_set", return_value=_credentials()
		)
		credentials.start()
		self.addCleanup(credentials.stop)
		self.refund_manager = given_user_with_role("Paymob Refund Manager")
		self.accounts_manager = given_user_with_role("Accounts Manager")

	def _charged_attempt(self, state="Paid", refunded_amount_cents=0, charged_cents=27555):
		attempt, request, invoice = given_attempt(state=state, credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		# LIFO teardown: registering this after cleanup_fixture makes it run first, so the
		# fixture cleanup (cancel/delete) always runs as Administrator even if the test
		# switched to a plain user to exercise the permission gate.
		self.addCleanup(frappe.set_user, "Administrator")
		if refunded_amount_cents:
			attempt.db_set("refunded_amount_cents", refunded_amount_cents)
		given_transaction(
			"Success",
			f"charge-{attempt.name}",
			attempt.name,
			request.name,
			amount_cents=charged_cents,
			processed=1,
		)
		return attempt


class TestRequestRefund(_RefundTestCase):
	def test_disabled_paymob_changes_nothing(self):
		attempt = self._charged_attempt()
		frappe.set_user(self.refund_manager)
		before_entries = payment_entry_count()
		with (
			patch("paymob_integration.paymob.settings.get_settings", return_value=frappe._dict(enabled=0)),
			patch("paymob_integration.paymob.refund.request") as refund,
			self.assertRaisesRegex(frappe.ValidationError, "Paymob is not enabled"),
		):
			api.request_refund(attempt.name, 10000)

		attempt.reload()
		self.assertIsNone(attempt.refund_requested_at)
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"attempt": attempt.name}), 0)
		self.assertEqual(payment_entry_count(), before_entries)
		refund.assert_not_called()

	def test_a_user_without_the_role_is_refused(self):
		attempt = self._charged_attempt()
		frappe.set_user(self.accounts_manager)
		with (
			patch("paymob_integration.paymob.settings.get_settings", return_value=frappe._dict(enabled=0)),
			patch("paymob_integration.paymob.refund.request") as refund,
		):
			with self.assertRaises(frappe.PermissionError):
				api.request_refund(attempt.name, 10000)
		refund.assert_not_called()

	def test_a_refund_manager_is_allowed(self):
		attempt = self._charged_attempt()
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.refund.request", return_value={}) as refund:
			api.request_refund(attempt.name, 10000)
		refund.assert_called_once()
		self.assertEqual(
			frappe.db.get_value(
				"Paymob Audit Entry", {"attempt": attempt.name, "event": "Refund Requested"}, "actor"
			),
			self.refund_manager,
		)

	def test_a_double_submitted_refund_makes_one_outbound_call(self):
		attempt = self._charged_attempt()
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.refund.request", return_value={}) as refund:
			api.request_refund(attempt.name, 10000)
			with self.assertRaises(frappe.ValidationError):
				api.request_refund(attempt.name, 10000)
		refund.assert_called_once()

	def test_an_amount_over_the_charged_amount_is_refused(self):
		attempt = self._charged_attempt(charged_cents=27555)
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.refund.request") as refund:
			with self.assertRaises(frappe.ValidationError):
				api.request_refund(attempt.name, 27556)
		refund.assert_not_called()

	def test_a_browser_supplied_transaction_id_is_ignored(self):
		attempt = self._charged_attempt()
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.refund.request", return_value={}) as refund:
			api.request_refund(attempt.name, 10000)
		self.assertEqual(refund.call_args.kwargs["transaction_id"], f"charge-{attempt.name}")

	def test_a_second_partial_refund_is_capped_by_the_running_total(self):
		attempt = self._charged_attempt(state="Partially Refunded", refunded_amount_cents=10000)
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.refund.request") as refund:
			with self.assertRaises(frappe.ValidationError):
				api.request_refund(attempt.name, 20000)  # remaining is 17555
		refund.assert_not_called()
		with patch("paymob_integration.paymob.refund.request", return_value={}) as refund:
			api.request_refund(attempt.name, 17555)
		refund.assert_called_once()

	def test_a_network_error_leaves_the_marker_set_and_the_ledger_untouched(self):
		attempt = self._charged_attempt()
		frappe.set_user(self.refund_manager)
		before = payment_entry_count()
		with patch(
			"paymob_integration.paymob.refund.request",
			side_effect=client.PaymobNetworkError("timeout"),
		):
			with self.assertRaises(client.PaymobNetworkError):
				api.request_refund(attempt.name, 10000)
		attempt.reload()
		self.assertIsNotNone(attempt.refund_requested_at)
		self.assertEqual(payment_entry_count(), before)

	def test_a_refund_on_a_pending_attempt_is_refused(self):
		attempt = self._charged_attempt(state="Pending")
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.refund.request") as refund:
			with self.assertRaises(frappe.ValidationError):
				api.request_refund(attempt.name, 10000)
		refund.assert_not_called()
