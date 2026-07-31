"""Capture requests use a verified authorization under the existing refund permission."""

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


class TestRequestCapture(NoCommitIntegrationTestCase):
	def setUp(self):
		credentials = patch(
			"paymob_integration.paymob.settings.get_credential_set", return_value=_credentials()
		)
		credentials.start()
		self.addCleanup(credentials.stop)
		self.refund_manager = given_user_with_role("Paymob Refund Manager")
		self.sales_user = given_user_with_role("Sales User")

	def _authorized_attempt(self, state="Authorized", with_authorization=True):
		attempt, request, invoice = given_attempt(state=state, credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		self.addCleanup(frappe.set_user, "Administrator")
		if with_authorization:
			given_transaction("Auth", f"auth-{attempt.name}", attempt.name, request.name, processed=1)
		return attempt

	def test_authorized_capture_uses_the_verified_authorization_once(self):
		attempt = self._authorized_attempt()
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.void_refund.capture", return_value={}) as capture:
			api.request_capture(attempt.name)
			with self.assertRaises(frappe.ValidationError):
				api.request_capture(attempt.name)
		capture.assert_called_once()
		self.assertEqual(
			capture.call_args.kwargs, {"transaction_id": f"auth-{attempt.name}", "amount_cents": 27555}
		)

	def test_permission_and_state_are_enforced_before_the_call(self):
		attempt = self._authorized_attempt()
		frappe.set_user(self.sales_user)
		with patch("paymob_integration.paymob.void_refund.capture") as capture:
			with self.assertRaises(frappe.PermissionError):
				api.request_capture(attempt.name)
		capture.assert_not_called()

	def test_network_error_keeps_the_latch_and_never_posts(self):
		attempt = self._authorized_attempt()
		frappe.set_user(self.refund_manager)
		before = payment_entry_count()
		with patch(
			"paymob_integration.paymob.void_refund.capture", side_effect=client.PaymobNetworkError("timeout")
		):
			with self.assertRaises(client.PaymobNetworkError):
				api.request_capture(attempt.name)
		attempt.reload()
		self.assertIsNotNone(attempt.capture_requested_at)
		self.assertEqual(payment_entry_count(), before)

	def test_capture_on_a_non_authorized_attempt_is_refused(self):
		attempt = self._authorized_attempt(state="Paid", with_authorization=False)
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.void_refund.capture") as capture:
			with self.assertRaises(frappe.ValidationError):
				api.request_capture(attempt.name)
		capture.assert_not_called()

	def test_capture_refused_while_a_refund_is_in_progress(self):
		attempt = self._authorized_attempt()
		attempt.db_set("refund_requested_at", frappe.utils.now_datetime())
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.void_refund.capture") as capture:
			with self.assertRaises(frappe.ValidationError):
				api.request_capture(attempt.name)
		capture.assert_not_called()

	def test_capture_without_a_verified_authorization_is_refused(self):
		attempt = self._authorized_attempt(with_authorization=False)
		frappe.set_user(self.refund_manager)
		with patch("paymob_integration.paymob.void_refund.capture") as capture:
			with self.assertRaises(frappe.ValidationError):
				api.request_capture(attempt.name)
		capture.assert_not_called()
