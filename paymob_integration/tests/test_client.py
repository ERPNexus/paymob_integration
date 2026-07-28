from unittest.mock import Mock, patch

from frappe.tests import UnitTestCase

from paymob_integration.paymob import client


class TestClient(UnitTestCase):
	@patch("paymob_integration.paymob.client.requests.request")
	def test_api_error_shows_only_allowlisted_paymob_detail(self, request):
		response = Mock(status_code=417)
		response.json.return_value = {
			"detail": "Refunds are not enabled for this transaction.",
			"auth_token": "must-not-reach-the-browser",
		}
		request.return_value = response

		with self.assertRaisesRegex(
			client.PaymobAPIError, "HTTP 417.*Refunds are not enabled for this transaction"
		) as raised:
			client.request("POST", "https://accept.example.test/refund")

		self.assertNotIn("must-not-reach-the-browser", str(raised.exception))
