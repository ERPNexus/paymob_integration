import hashlib
import hmac as hmac_lib
from unittest.mock import Mock, patch

import frappe

from paymob_integration.paymob.hmac_verify import RESPONSE_CALLBACK_FIELDS
from paymob_integration.tests.helpers import NoCommitIntegrationTestCase, given_submitted_payment_request
from paymob_integration.www import paymob_result

SECRET = "hmac_test_FAKE_secret"


def _signed_query(merchant_order_id, order_id, secret=SECRET):
	fields = dict.fromkeys(RESPONSE_CALLBACK_FIELDS, "")
	fields.update({"order": order_id, "success": "true"})
	message = "".join(fields[field] for field in RESPONSE_CALLBACK_FIELDS)
	digest = hmac_lib.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()
	return {**fields, "merchant_order_id": merchant_order_id, "hmac": digest}


class TestResultPage(NoCommitIntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.payment_request, self.invoice = given_submitted_payment_request()
		self.attempt = frappe.get_doc(
			{
				"doctype": "Paymob Payment Attempt",
				"special_reference": f"{self.payment_request.name}-1",
				"payment_request": self.payment_request.name,
				"state": "Paid",
				"expected_amount_cents": 27555,
				"currency": "EGP",
				"country": "Egypt",
				"mode": "Test",
				"paymob_order_id": "987654321",
			}
		).insert(ignore_permissions=True)
		self.credentials = Mock()
		self.credentials.get_password.return_value = SECRET

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.delete_doc("Paymob Payment Attempt", self.attempt.name, force=True)
		self.payment_request.cancel()
		frappe.delete_doc("Payment Request", self.payment_request.name, force=True)
		self.invoice.cancel()
		frappe.delete_doc("Sales Invoice", self.invoice.name, force=True)
		super().tearDown()

	def render(self, form_dict):
		frappe.form_dict.clear()
		frappe.form_dict.update(form_dict)
		with patch(
			"paymob_integration.www.paymob_result.settings.get_credential_set",
			return_value=self.credentials,
		):
			return paymob_result.get_context(frappe._dict())

	def test_paid_attempt_with_valid_signature_renders_paid(self):
		context = self.render(_signed_query(self.attempt.name, self.attempt.paymob_order_id))
		self.assertEqual(context.state, "Paid")

	def test_paid_attempt_with_bad_signature_renders_pending(self):
		query = _signed_query(self.attempt.name, self.attempt.paymob_order_id)
		query["hmac"] = "0" * 128
		context = self.render(query)
		self.assertEqual(context.state, "Pending")

	def test_unknown_reference_renders_neutral_without_raising(self):
		context = self.render({"merchant_order_id": "does-not-exist"})
		self.assertEqual(context.state, "Pending")

	def test_no_params_at_all_renders_neutral(self):
		context = self.render({})
		self.assertEqual(context.state, "Pending")

	def test_signed_order_for_a_different_attempt_renders_pending(self):
		# A genuinely signed redirect for some other order, replayed against this attempt's
		# unsigned merchant_order_id lookup key, must not borrow this attempt's real state.
		query = _signed_query(self.attempt.name, "someone-elses-order-id")
		context = self.render(query)
		self.assertEqual(context.state, "Pending")

	def test_missing_paymob_order_id_renders_pending(self):
		attempt = frappe.get_doc(
			{
				"doctype": "Paymob Payment Attempt",
				"special_reference": f"{self.payment_request.name}-2",
				"payment_request": self.payment_request.name,
				"state": "Paid",
				"expected_amount_cents": 27555,
				"currency": "EGP",
				"country": "Egypt",
				"mode": "Test",
			}
		).insert(ignore_permissions=True)
		try:
			context = self.render(_signed_query(attempt.name, ""))
			self.assertEqual(context.state, "Pending")
		finally:
			frappe.delete_doc("Paymob Payment Attempt", attempt.name, force=True)

	def test_uses_attempts_stored_mode_for_credential_lookup(self):
		frappe.form_dict.clear()
		frappe.form_dict.update(_signed_query(self.attempt.name, self.attempt.paymob_order_id))
		with patch(
			"paymob_integration.www.paymob_result.settings.get_credential_set",
			return_value=self.credentials,
		) as get_credential_set:
			paymob_result.get_context(frappe._dict())
		get_credential_set.assert_called_once_with("Egypt", "EGP", "Test")

	def test_credential_lookup_failure_is_logged_and_renders_pending(self):
		frappe.form_dict.clear()
		frappe.form_dict.update(_signed_query(self.attempt.name, self.attempt.paymob_order_id))
		with (
			patch(
				"paymob_integration.www.paymob_result.settings.get_credential_set",
				side_effect=frappe.ValidationError,
			),
			patch("paymob_integration.www.paymob_result.frappe.logger") as logger,
		):
			context = paymob_result.get_context(frappe._dict())

		self.assertEqual(context.state, "Pending")
		logged = " ".join(str(call) for call in logger.return_value.info.call_args_list)
		self.assertIn("credential_lookup_failed", logged)
		self.assertIn(self.payment_request.name, logged)

	def test_authorized_attempt_renders_the_authorized_message(self):
		attempt = frappe.get_doc(
			{
				"doctype": "Paymob Payment Attempt",
				"special_reference": f"{self.payment_request.name}-3",
				"payment_request": self.payment_request.name,
				"state": "Authorized",
				"expected_amount_cents": 27555,
				"currency": "EGP",
				"country": "Egypt",
				"mode": "Test",
				"paymob_order_id": "authorized-order",
			}
		).insert(ignore_permissions=True)
		try:
			context = self.render(_signed_query(attempt.name, attempt.paymob_order_id))
			self.assertEqual(context.state, "Authorized")
			self.assertEqual(context.message, "Your payment has been authorized and is awaiting capture.")
		finally:
			frappe.delete_doc("Paymob Payment Attempt", attempt.name, force=True)

	def test_rendering_writes_nothing(self):
		before_modified = frappe.db.get_value("Paymob Payment Attempt", self.attempt.name, "modified")
		before_entries = frappe.db.count("Payment Entry")

		self.render(_signed_query(self.attempt.name, self.attempt.paymob_order_id))

		self.assertEqual(frappe.db.count("Payment Entry"), before_entries)
		self.assertEqual(
			frappe.db.get_value("Paymob Payment Attempt", self.attempt.name, "modified"),
			before_modified,
		)
