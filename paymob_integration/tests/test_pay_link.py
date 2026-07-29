from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from paymob_integration import api, pay_link, payment_request


class TestPayLink(UnitTestCase):
	def test_build_uses_frappe_signed_params(self):
		with (
			patch("paymob_integration.pay_link.get_url", return_value="https://site.test"),
			patch(
				"paymob_integration.pay_link.get_signed_params", return_value="ref=PR-0001&_signature=signed"
			),
		):
			self.assertEqual(
				pay_link.build("PR-0001"), "https://site.test/paymob-pay?ref=PR-0001&_signature=signed"
			)

	def test_payment_request_hook_only_sets_a_valid_paymob_link(self):
		doc = frappe._dict(
			name="PR-0001",
			payment_request_type="Inward",
			reference_doctype="Sales Invoice",
			reference_name="SINV-0001",
			currency="EGP",
			message=None,
		)
		with (
			patch(
				"paymob_integration.payment_request.settings.get_settings",
				return_value=Mock(enabled=1, send_payment_link_email=1),
			),
			patch(
				"paymob_integration.payment_request.frappe.get_doc",
				return_value=frappe._dict(company="Egypt Company"),
			),
			patch("paymob_integration.payment_request.api._merchant_country", return_value="Egypt"),
			patch("paymob_integration.payment_request.settings.get_credential_set"),
			patch(
				"paymob_integration.payment_request.pay_link.build",
				return_value="https://site.test/paymob-pay?signed",
			),
		):
			payment_request.set_payment_url(doc)

		self.assertEqual(doc.payment_url, "https://site.test/paymob-pay?signed")
		self.assertIn("payment_url", doc.message)

	def test_checkout_reuses_a_ready_pending_attempt(self):
		request = frappe._dict(name="PR-0001")
		attempt = Mock(country="Egypt", currency="EGP", mode="Test")
		attempt.name = "PR-0001-1"
		attempt.get_password.return_value = "client-secret"
		credentials = Mock()
		with (
			patch("paymob_integration.api._validate_payable"),
			patch("paymob_integration.api._active_attempt", return_value=attempt),
			patch("paymob_integration.api.settings.get_credential_set", return_value=credentials),
			patch("paymob_integration.api.build_checkout_url", return_value="https://checkout.test"),
		):
			result = api._checkout(request, reuse_pending=True)

		self.assertEqual(result, {"attempt": "PR-0001-1", "checkout_url": "https://checkout.test"})

	def test_contact_email_uses_the_same_fallback_as_billing_data(self):
		request = frappe._dict(email_to="payer@example.test")
		self.assertEqual(api._contact_email(request, frappe._dict(contact_email=None)), "payer@example.test")
