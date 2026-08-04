from unittest.mock import patch
import frappe
from frappe.tests.utils import FrappeTestCase

from paymob_integration.paymob import client
from paymob_integration.paymob_integration.doctype.paymob_settings.paymob_settings import test_connection


class TestPaymobSettings(FrappeTestCase):
	@patch("paymob_integration.paymob_integration.doctype.paymob_settings.paymob_settings.frappe.only_for")
	@patch(
		"paymob_integration.paymob_integration.doctype.paymob_settings.paymob_settings.settings.get_credential_set"
	)
	@patch(
		"paymob_integration.paymob_integration.doctype.paymob_settings.paymob_settings.auth.get_auth_token"
	)
	def test_connection_surfaces_paymob_errors(self, get_auth_token, get_credential_set, only_for):
		get_credential_set.return_value = frappe._dict(country="Egypt", mode="Test")
		get_auth_token.side_effect = client.PaymobAPIError(
			"Paymob rejected the request. Check the credentials and try again.", 401
		)
		frappe.local.message_log = []

		with self.assertRaisesRegex(frappe.ValidationError, "Paymob rejected the request"):
			test_connection("Egypt", "EGP")

		self.assertEqual(
			frappe.local.message_log[-1]["message"],
			"Paymob rejected the request. Check the credentials and try again.",
		)
