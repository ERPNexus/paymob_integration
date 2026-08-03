from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from paymob_integration import api
from paymob_integration.paymob import intention
from paymob_integration.paymob.client import PaymobNetworkError
from paymob_integration.tests.helpers import NoCommitIntegrationTestCase, given_submitted_payment_request

INTENTION_RESPONSE = {
	"id": "pi_FAKE_1",
	"intention_order_id": 987654,
	"client_secret": "egy_csk_FAKE_1",
}

CHECKOUT_RESULT = {
	"intention_id": "pi_FAKE_1",
	"order_id": "987654",
	"client_secret": "egy_csk_FAKE_1",
}


class TestCreateIntention(UnitTestCase):
	def setUp(self):
		self.credentials = _Credentials()

	def call(self, **overrides):
		payload = {
			"amount_cents": 27555,
			"currency": "EGP",
			"special_reference": "PR-00042-1",
			"billing_data": {"email": "a@b.test", "phone_number": "+201000000000"},
			"items": [],
			"notification_url": "https://site.test/api/method/webhook",
			"redirection_url": "https://site.test/paymob-result",
			"expiration": 3600,
			"integration_ids": ["1234"],
		}
		payload.update(overrides)
		return intention.create_intention(self.credentials, **payload)

	def test_returns_the_three_identifiers(self):
		with patch("paymob_integration.paymob.intention.client.request", return_value=INTENTION_RESPONSE):
			result = self.call()

		self.assertEqual(
			result,
			{
				"intention_id": "pi_FAKE_1",
				"order_id": "987654",
				"client_secret": "egy_csk_FAKE_1",
			},
		)

	def test_authenticates_with_the_secret_key(self):
		with patch(
			"paymob_integration.paymob.intention.client.request", return_value=INTENTION_RESPONSE
		) as mocked:
			self.call()

		self.assertEqual(mocked.call_args.kwargs["headers"]["Authorization"], "Token sk_test_FAKE_secret")

	def test_sends_the_amount_as_an_integer(self):
		with patch(
			"paymob_integration.paymob.intention.client.request", return_value=INTENTION_RESPONSE
		) as mocked:
			self.call()

		body = mocked.call_args.kwargs["json_body"]
		self.assertIsInstance(body["amount"], int)
		self.assertEqual(body["amount"], 27555)
		self.assertEqual(body["payment_methods"], [1234])

	def test_sends_every_integration_id_it_is_given(self):
		with patch(
			"paymob_integration.paymob.intention.client.request", return_value=INTENTION_RESPONSE
		) as mocked:
			self.call(integration_ids=["1002", "1003"])

		self.assertEqual(mocked.call_args.kwargs["json_body"]["payment_methods"], [1002, 1003])


class _Credentials:
	base_url = "https://accept.paymob.test"
	country = "Egypt"

	def get_password(self, fieldname):
		assert fieldname == "secret_key"
		return "sk_test_FAKE_secret"


class TestCheckoutURL(UnitTestCase):
	def test_only_browser_safe_values_are_in_the_url(self):
		credentials = Mock(
			public_key="pk_test_FAKE_public",
			base_url="https://accept.paymob.test/",
		)
		with patch("paymob_integration.api.settings.base_url", return_value=credentials.base_url):
			url = api.build_checkout_url(credentials, "egy_csk_FAKE_1")

		self.assertIn("publicKey=pk_test_FAKE_public", url)
		self.assertIn("clientSecret=egy_csk_FAKE_1", url)
		self.assertNotIn("sk_test_FAKE_secret", url)

	def test_paymob_region_comes_from_the_company(self):
		request = frappe._dict(company="Egypt Company")
		with patch("paymob_integration.api.frappe.get_cached_value", return_value="Egypt"):
			self.assertEqual(api._merchant_country(request, frappe._dict()), "Egypt")

	def test_paymob_region_falls_back_to_the_linked_document_company(self):
		request = frappe._dict(company=None, reference_doctype="Sales Invoice", reference_name="SINV-00001")
		with (
			patch("paymob_integration.api.frappe.get_cached_value", return_value="Egypt"),
		):
			self.assertEqual(api._merchant_country(request, frappe._dict(company="Egypt Company")), "Egypt")

	def test_missing_company_has_an_explicit_error(self):
		request = frappe._dict(company=None, reference_doctype="Sales Invoice", reference_name="SINV-00001")
		with (
			self.assertRaisesRegex(frappe.ValidationError, "Payment Request needs a company"),
		):
			api._merchant_country(request, frappe._dict())

	def test_customer_country_falls_back_to_the_partys_primary_address(self):
		request = frappe._dict(party_type="Customer", party="CUST-00001")
		source = frappe._dict(customer_address=None)
		with (
			patch("paymob_integration.api.get_default_address", return_value="ADDR-00001"),
			patch("paymob_integration.api.frappe.db.get_value", side_effect=["Saudi Arabia", "sa"]),
		):
			self.assertEqual(api._billing_country(request, source), "SA")

	def test_customer_country_uses_paymobs_placeholder_when_no_address_exists(self):
		request = frappe._dict(party_type="Customer", party="CUST-00001")
		source = frappe._dict(customer_address=None)
		with patch("paymob_integration.api.get_default_address", return_value=None):
			self.assertEqual(api._billing_country(request, source), "NA")

	def test_zero_amount_is_refused_before_checkout(self):
		request = frappe._dict(
			docstatus=1,
			payment_request_type="Inward",
			status="Requested",
			grand_total=0,
			currency="EGP",
			reference_doctype="Sales Invoice",
			reference_name="SINV-00001",
		)
		with self.assertRaisesRegex(frappe.ValidationError, "must be greater than zero"):
			api._validate_payable(request)

	def test_start_checkout_persists_identifiers_before_returning(self):
		request = Mock(
			docstatus=1,
			payment_request_type="Inward",
			status="Requested",
			grand_total="275.55",
			currency="EGP",
		)
		credentials = Mock(country="Egypt", mode="Test", public_key="pk_test_FAKE_public")
		request.name = "ACC-PRQ-00001"
		attempt = Mock(
			expected_amount_cents=27555,
			currency="EGP",
			special_reference="ACC-PRQ-00001-1",
		)
		attempt.name = "ACC-PRQ-00001-1"
		with (
			patch("paymob_integration.api.frappe.get_doc", return_value=request),
			patch("paymob_integration.api._merchant_country", return_value="Egypt"),
			patch(
				"paymob_integration.api.settings.resolve_integrations",
				return_value=("Auto Capture", ["1234"]),
			),
			patch("paymob_integration.api.settings.get_credential_set", return_value=credentials),
			patch("paymob_integration.api._create_attempt", return_value=attempt),
			patch(
				"paymob_integration.api.intention.create_intention",
				return_value={
					"intention_id": "pi_FAKE_1",
					"order_id": "987654",
					"client_secret": "egy_csk_FAKE_1",
				},
			),
			patch("paymob_integration.api._billing_data", return_value={}),
			patch("paymob_integration.api._items", return_value=[]),
			patch(
				"paymob_integration.api.settings.get_settings",
				return_value=Mock(intention_expiration_seconds=3600),
			),
			patch(
				"paymob_integration.api.get_url",
				side_effect=["https://site.test/webhook", "https://site.test/result"],
			),
			patch("paymob_integration.api.build_checkout_url", return_value="https://checkout.test"),
		):
			result = api.start_checkout(request.name)

		request.check_permission.assert_called_once_with("write")
		attempt.update.assert_called_once_with(
			{"paymob_intention_id": "pi_FAKE_1", "paymob_order_id": "987654"}
		)
		attempt.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(result, {"attempt": attempt.name, "checkout_url": "https://checkout.test"})

	def test_pending_attempt_from_the_other_capture_mode_is_not_reused(self):
		request = frappe._dict(
			name="PR-0001",
			reference_doctype="Sales Invoice",
			reference_name="SINV-0001",
			currency="EGP",
		)
		pending = Mock(country="Egypt", currency="EGP", mode="Test", authorize_only=0)
		pending.name = "PR-0001-1"
		new_attempt = Mock(expected_amount_cents=27555, currency="EGP", special_reference="PR-0001-2")
		new_attempt.name = "PR-0001-2"
		with (
			patch("paymob_integration.api._validate_payable"),
			patch("paymob_integration.api.frappe.get_doc", return_value=frappe._dict()),
			patch("paymob_integration.api._merchant_country", return_value="Egypt"),
			patch(
				"paymob_integration.api.settings.resolve_integrations",
				return_value=("Authorize Only", ["1002"]),
			),
			patch("paymob_integration.api._active_attempt", return_value=pending),
			patch(
				"paymob_integration.api.settings.get_credential_set",
				return_value=Mock(country="Egypt", mode="Test"),
			),
			patch("paymob_integration.api._create_attempt", return_value=new_attempt),
			patch("paymob_integration.api.intention.create_intention", return_value=CHECKOUT_RESULT),
			patch("paymob_integration.api._billing_data", return_value={}),
			patch("paymob_integration.api._items", return_value=[]),
			patch(
				"paymob_integration.api.settings.get_settings",
				return_value=Mock(intention_expiration_seconds=3600),
			),
			patch(
				"paymob_integration.api.get_url",
				side_effect=["https://site.test/webhook", "https://site.test/result"],
			),
			patch("paymob_integration.api.build_checkout_url", return_value="https://checkout.test"),
		):
			result = api._checkout(request, reuse_pending=True)

		self.assertEqual(result["attempt"], "PR-0001-2")


class TestStartCheckout(NoCommitIntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.payment_request, self.invoice = given_submitted_payment_request()
		self.credentials = Mock(country="Egypt", mode="Test", public_key="pk_test_FAKE_public")
		self.config = frappe._dict(intention_expiration_seconds=3600)

	def tearDown(self):
		frappe.set_user("Administrator")
		for attempt in frappe.get_all(
			"Paymob Payment Attempt", {"payment_request": self.payment_request.name}, pluck="name"
		):
			frappe.delete_doc("Paymob Payment Attempt", attempt, force=True)
		self.payment_request.cancel()
		frappe.delete_doc("Payment Request", self.payment_request.name, force=True)
		self.invoice.cancel()
		frappe.delete_doc("Sales Invoice", self.invoice.name, force=True)
		super().tearDown()

	def start(self, intention_result=CHECKOUT_RESULT, intention_error=None):
		with (
			patch("paymob_integration.api.settings.get_credential_set", return_value=self.credentials),
			patch("paymob_integration.api.settings.get_settings", return_value=self.config),
			patch(
				"paymob_integration.api.settings.resolve_integrations",
				return_value=("Auto Capture", ["1234"]),
			),
			patch(
				"paymob_integration.api.intention.create_intention",
				return_value=intention_result,
				side_effect=intention_error,
			),
		):
			return api.start_checkout(self.payment_request.name)

	def test_freezes_amount_and_persists_identifiers(self):
		result = self.start()
		attempt = frappe.get_doc("Paymob Payment Attempt", result["attempt"])

		self.assertEqual(attempt.expected_amount_cents, 27555)
		self.assertEqual(attempt.state, "Pending")
		self.assertEqual(attempt.paymob_intention_id, "pi_FAKE_1")
		self.assertEqual(attempt.paymob_order_id, "987654")

	def test_network_failure_keeps_pending_attempt_without_identifiers(self):
		with self.assertRaises(PaymobNetworkError):
			self.start(intention_error=PaymobNetworkError("down"))

		attempt = frappe.get_last_doc(
			"Paymob Payment Attempt", filters={"payment_request": self.payment_request.name}
		)
		self.assertEqual(attempt.state, "Pending")
		self.assertFalse(attempt.paymob_intention_id)
		self.assertFalse(attempt.paymob_order_id)

	def test_retry_creates_a_second_attempt(self):
		first = self.start()
		second = self.start()

		self.assertNotEqual(first["attempt"], second["attempt"])
		self.assertEqual(
			frappe.db.count("Paymob Payment Attempt", {"payment_request": self.payment_request.name}), 2
		)

	def test_user_without_permission_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			api.start_checkout(self.payment_request.name)

	def test_sends_every_configured_integration_id(self):
		with (
			patch(
				"paymob_integration.api.settings.resolve_integrations",
				return_value=("Authorize Only", ["1002", "1003"]),
			) as resolve_integrations,
			patch("paymob_integration.api.settings.get_credential_set", return_value=self.credentials),
			patch("paymob_integration.api.settings.get_settings", return_value=self.config),
			patch(
				"paymob_integration.api.intention.create_intention", return_value=CHECKOUT_RESULT
			) as create_intention,
		):
			api.start_checkout(self.payment_request.name)

		resolve_integrations.assert_called_once_with("Egypt", "EGP")
		self.assertEqual(create_intention.call_args.kwargs["integration_ids"], ["1002", "1003"])

	def test_configured_authorize_only_marks_the_attempt(self):
		with (
			patch(
				"paymob_integration.api.settings.resolve_integrations",
				return_value=("Authorize Only", ["1002"]),
			),
			patch("paymob_integration.api.settings.get_credential_set", return_value=self.credentials),
			patch("paymob_integration.api.settings.get_settings", return_value=self.config),
			patch(
				"paymob_integration.api.intention.create_intention", return_value=CHECKOUT_RESULT
			) as create_intention,
		):
			result = api.start_checkout(self.payment_request.name)

		self.assertEqual(create_intention.call_args.kwargs["integration_ids"], ["1002"])
		attempt = frappe.get_doc("Paymob Payment Attempt", result["attempt"])
		self.assertTrue(attempt.authorize_only)

	def test_configured_auto_capture_leaves_the_attempt_unmarked(self):
		with (
			patch(
				"paymob_integration.api.settings.resolve_integrations",
				return_value=("Auto Capture", ["1001"]),
			),
			patch("paymob_integration.api.settings.get_credential_set", return_value=self.credentials),
			patch("paymob_integration.api.settings.get_settings", return_value=self.config),
			patch("paymob_integration.api.intention.create_intention", return_value=CHECKOUT_RESULT),
		):
			result = api.start_checkout(self.payment_request.name)

		attempt = frappe.get_doc("Paymob Payment Attempt", result["attempt"])
		self.assertFalse(attempt.authorize_only)

	def test_a_misconfigured_group_throws_before_paymob_is_called(self):
		with (
			patch(
				"paymob_integration.api.settings.resolve_integrations",
				side_effect=frappe.ValidationError("Mixed Capture Modes"),
			),
			patch("paymob_integration.paymob.intention.client.request") as client_request,
			patch("paymob_integration.api.intention.create_intention") as create_intention,
		):
			with self.assertRaises(frappe.ValidationError):
				api.start_checkout(self.payment_request.name)

		client_request.assert_not_called()
		create_intention.assert_not_called()
