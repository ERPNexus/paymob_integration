from unittest.mock import Mock, patch

from frappe.tests import UnitTestCase

from paymob_integration.paymob import refund


class TestRefundClient(UnitTestCase):
	def test_refund_posts_the_verified_amount_once(self):
		credentials = Mock(base_url="https://accept.example.test")
		with (
			patch("paymob_integration.paymob.refund.auth.get_auth_token", return_value="token"),
			patch("paymob_integration.paymob.refund.client.request", return_value={}) as request,
		):
			refund.request(credentials, transaction_id="123", amount_cents=10000)
		request.assert_called_once_with(
			"POST", "https://accept.example.test/api/acceptance/void_refund/refund",
			json_body={"auth_token": "token", "transaction_id": "123", "amount_cents": 10000},
		)
