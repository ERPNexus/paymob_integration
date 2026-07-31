"""The outbound reversal calls are deliberately thin and never retry."""

from unittest.mock import Mock, patch

from frappe.tests import UnitTestCase

from paymob_integration.paymob import client, void_refund


class TestVoidRefund(UnitTestCase):
	def setUp(self):
		self.credentials = Mock()
		self.credentials.base_url = "https://accept.example.test"
		self.auth = patch("paymob_integration.paymob.void_refund.auth.get_auth_token", return_value="token")
		self.auth.start()
		self.addCleanup(self.auth.stop)

	def test_refund_posts_the_verified_amount_once(self):
		with patch("paymob_integration.paymob.void_refund.client.request", return_value={}) as request:
			void_refund.refund(self.credentials, transaction_id="123", amount_cents=10000)

		request.assert_called_once_with(
			"POST",
			"https://accept.example.test/api/acceptance/void_refund/refund",
			json_body={"auth_token": "token", "transaction_id": "123", "amount_cents": 10000},
		)

	def test_paymob_errors_propagate_without_a_retry(self):
		with patch(
			"paymob_integration.paymob.void_refund.client.request",
			side_effect=client.PaymobAPIError("rejected"),
		) as request:
			with self.assertRaises(client.PaymobAPIError):
				void_refund.void(self.credentials, transaction_id="123")

		request.assert_called_once()

	def test_capture_posts_the_verified_amount_once(self):
		with patch("paymob_integration.paymob.void_refund.client.request", return_value={}) as request:
			void_refund.capture(self.credentials, transaction_id="123", amount_cents=10000)

		request.assert_called_once_with(
			"POST",
			"https://accept.example.test/api/acceptance/capture",
			json_body={"auth_token": "token", "transaction_id": "123", "amount_cents": 10000},
		)
