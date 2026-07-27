"""Endpoint tests for the processed callback, driven through a real werkzeug request so the
frappe.form_dict / request.args split (the make_form_dict landmine, see webhooks.py) is actually
exercised rather than assumed. The no-commit integration base is required because the storage path (Phase 05) writes
real Paymob Transaction rows.
"""

import json
from unittest.mock import Mock, patch

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from paymob_integration import webhooks
from paymob_integration.tests.helpers import NoCommitIntegrationTestCase, given_submitted_payment_request
from paymob_integration.tests.test_hmac_verify import SECRET, VALID_OBJ, _sign_processed


def _credentials(secret=SECRET, mode="Test"):
	row = Mock()
	row.get_password.return_value = secret
	row.mode = mode
	return row


def _post(payload, hmac):
	"""hmac=None means no `?hmac=` on the URL at all, even if `payload` has an "hmac" key."""
	query_string = {"hmac": hmac} if hmac is not None else {}
	environ = EnvironBuilder(method="POST", query_string=query_string, json=payload).get_environ()
	frappe.local.request = Request(environ)
	frappe.local.form_dict = frappe._dict(payload)
	return webhooks.processed_callback()


class TestProcessedCallback(NoCommitIntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.local.response = frappe._dict()

	def tearDown(self):
		frappe.local.request = None
		frappe.db.delete("Paymob Transaction", {"paymob_transaction_id": VALID_OBJ["id"]})
		super().tearDown()

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_authentic_callback_is_accepted(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]
		digest = _sign_processed(VALID_OBJ)

		result = _post({"obj": VALID_OBJ}, digest)

		self.assertEqual(result, "ok")
		self.assertNotIn("http_status_code", frappe.local.response)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_wrong_secret_is_refused(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials(secret="other_secret")]
		digest = _sign_processed(VALID_OBJ)

		result = _post({"obj": VALID_OBJ}, digest)

		self.assertIsNone(result)
		self.assertEqual(frappe.local.response["http_status_code"], 401)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_tampered_amount_is_refused(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]
		digest = _sign_processed(VALID_OBJ)
		obj = {**VALID_OBJ, "amount_cents": 1}

		_post({"obj": obj}, digest)

		self.assertEqual(frappe.local.response["http_status_code"], 401)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_missing_hmac_query_param_is_refused(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]

		_post({"obj": VALID_OBJ}, None)

		self.assertEqual(frappe.local.response["http_status_code"], 401)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_hmac_in_body_only_is_refused(self, enabled_credential_sets):
		"""Locks in that we read request.args, not form_dict."""
		enabled_credential_sets.return_value = [_credentials()]
		digest = _sign_processed(VALID_OBJ)

		_post({"obj": VALID_OBJ, "hmac": digest}, None)

		self.assertEqual(frappe.local.response["http_status_code"], 401)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_second_credential_set_matches(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials(secret="wrong_secret"), _credentials()]
		digest = _sign_processed(VALID_OBJ)

		result = _post({"obj": VALID_OBJ}, digest)

		self.assertEqual(result, "ok")

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_paymob_disabled_returns_401_without_raising(self, enabled_credential_sets):
		enabled_credential_sets.return_value = []

		_post({"obj": VALID_OBJ}, "deadbeef")

		self.assertEqual(frappe.local.response["http_status_code"], 401)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_missing_obj_is_refused_without_raising(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]

		_post({}, "deadbeef")

		self.assertEqual(frappe.local.response["http_status_code"], 401)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_refused_callback_stores_nothing(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials(secret="other_secret")]
		digest = _sign_processed(VALID_OBJ)

		_post({"obj": VALID_OBJ}, digest)

		self.assertEqual(frappe.db.count("Paymob Transaction", {"paymob_transaction_id": VALID_OBJ["id"]}), 0)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_authentic_callback_is_stored(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]
		digest = _sign_processed(VALID_OBJ)

		_post({"obj": VALID_OBJ}, digest)

		txn = frappe.get_doc("Paymob Transaction", "123456:Success")
		self.assertEqual(txn.amount_cents, 27555)
		self.assertEqual(txn.currency, "EGP")
		self.assertEqual(txn.source, "Webhook")
		self.assertEqual(txn.hmac_verified, 1)
		self.assertEqual(txn.processed, 0)
		self.assertEqual(json.loads(txn.raw_payload), VALID_OBJ)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_duplicate_delivery_stores_once(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]
		digest = _sign_processed(VALID_OBJ)

		first = _post({"obj": VALID_OBJ}, digest)
		second = _post({"obj": VALID_OBJ}, digest)

		self.assertEqual(first, "ok")
		self.assertEqual(second, "ok")
		self.assertEqual(frappe.db.count("Paymob Transaction", {"paymob_transaction_id": VALID_OBJ["id"]}), 1)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_refund_after_success_stores_two_rows(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]
		_post({"obj": VALID_OBJ}, _sign_processed(VALID_OBJ))

		refund_obj = {**VALID_OBJ, "is_refunded": True, "refunded_amount_cents": 10000}
		_post({"obj": refund_obj}, _sign_processed(refund_obj))

		self.assertTrue(frappe.db.exists("Paymob Transaction", "123456:Success"))
		self.assertTrue(frappe.db.exists("Paymob Transaction", "123456:Refund:10000"))

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_partial_refunds_store_distinct_rows(self, enabled_credential_sets):
		"""Paymob resends the same parent transaction id per cumulative partial refund, with a
		growing refunded_amount_cents (plans/11-refund-and-void.md) — each step must be its own
		row, not collapsed by the dedup key into a single Refund row.
		"""
		enabled_credential_sets.return_value = [_credentials()]
		first_refund = {**VALID_OBJ, "is_refunded": True, "refunded_amount_cents": 10000}
		second_refund = {**VALID_OBJ, "is_refunded": True, "refunded_amount_cents": 20000}

		_post({"obj": first_refund}, _sign_processed(first_refund))
		_post({"obj": second_refund}, _sign_processed(second_refund))

		self.assertTrue(frappe.db.exists("Paymob Transaction", "123456:Refund:10000"))
		self.assertTrue(frappe.db.exists("Paymob Transaction", "123456:Refund:20000"))
		self.assertEqual(
			frappe.db.count(
				"Paymob Transaction", {"paymob_transaction_id": VALID_OBJ["id"], "event_kind": "Refund"}
			),
			2,
		)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_duplicate_refund_same_amount_is_deduped(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]
		refund_obj = {**VALID_OBJ, "is_refunded": True, "refunded_amount_cents": 10000}

		first = _post({"obj": refund_obj}, _sign_processed(refund_obj))
		second = _post({"obj": refund_obj}, _sign_processed(refund_obj))

		self.assertEqual(first, "ok")
		self.assertEqual(second, "ok")
		self.assertEqual(
			frappe.db.count(
				"Paymob Transaction", {"paymob_transaction_id": VALID_OBJ["id"], "event_kind": "Refund"}
			),
			1,
		)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_raw_payload_redacts_unlisted_fields(self, enabled_credential_sets):
		"""Real Paymob payloads carry billing_data (customer name/email/phone) beyond the fields
		this app uses — rules/stored-payment-data.md forbids a second copy of that inside raw_payload.
		"""
		enabled_credential_sets.return_value = [_credentials()]
		obj = {**VALID_OBJ, "billing_data": {"email": "customer@example.com", "phone_number": "0100"}}
		digest = _sign_processed(obj)

		_post({"obj": obj}, digest)

		txn = frappe.get_doc("Paymob Transaction", "123456:Success")
		stored = json.loads(txn.raw_payload)
		self.assertNotIn("billing_data", stored)
		self.assertEqual(stored["id"], VALID_OBJ["id"])

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_known_merchant_order_id_resolves_attempt(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]
		payment_request, invoice = given_submitted_payment_request()
		attempt = frappe.get_doc(
			{
				"doctype": "Paymob Payment Attempt",
				"special_reference": f"{payment_request.name}-1",
				"payment_request": payment_request.name,
				"expected_amount_cents": 27555,
				"currency": "EGP",
				"country": "Egypt",
				"mode": "Test",
				"paymob_order_id": str(VALID_OBJ["order"]["id"]),
			}
		).insert(ignore_permissions=True)
		obj = {**VALID_OBJ, "order": {**VALID_OBJ["order"], "merchant_order_id": attempt.name}}

		try:
			_post({"obj": obj}, _sign_processed(obj))

			txn = frappe.get_doc("Paymob Transaction", "123456:Success")
			self.assertEqual(txn.attempt, attempt.name)
			self.assertEqual(txn.payment_request, payment_request.name)
		finally:
			frappe.delete_doc("Paymob Payment Attempt", attempt.name, force=True)
			payment_request.cancel()
			frappe.delete_doc("Payment Request", payment_request.name, force=True)
			invoice.cancel()
			frappe.delete_doc("Sales Invoice", invoice.name, force=True)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_mismatched_order_id_does_not_resolve_attempt(self, enabled_credential_sets):
		"""merchant_order_id is unsigned — a genuine callback for order 987654 must not adopt
		an attempt whose own frozen paymob_order_id is a different order.
		"""
		enabled_credential_sets.return_value = [_credentials()]
		payment_request, invoice = given_submitted_payment_request()
		attempt = frappe.get_doc(
			{
				"doctype": "Paymob Payment Attempt",
				"special_reference": f"{payment_request.name}-1",
				"payment_request": payment_request.name,
				"expected_amount_cents": 27555,
				"currency": "EGP",
				"country": "Egypt",
				"mode": "Test",
				"paymob_order_id": "999999",
			}
		).insert(ignore_permissions=True)
		obj = {**VALID_OBJ, "order": {**VALID_OBJ["order"], "merchant_order_id": attempt.name}}

		try:
			_post({"obj": obj}, _sign_processed(obj))

			txn = frappe.get_doc("Paymob Transaction", "123456:Success")
			self.assertFalse(txn.attempt)
			self.assertFalse(txn.payment_request)
		finally:
			frappe.delete_doc("Paymob Payment Attempt", attempt.name, force=True)
			payment_request.cancel()
			frappe.delete_doc("Payment Request", payment_request.name, force=True)
			invoice.cancel()
			frappe.delete_doc("Sales Invoice", invoice.name, force=True)

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_unknown_merchant_order_id_stores_with_blank_links(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]
		digest = _sign_processed(VALID_OBJ)  # VALID_OBJ's merchant_order_id resolves to nothing

		result = _post({"obj": VALID_OBJ}, digest)

		self.assertEqual(result, "ok")
		txn = frappe.get_doc("Paymob Transaction", "123456:Success")
		self.assertFalse(txn.attempt)
		self.assertFalse(txn.payment_request)

	@patch("paymob_integration.webhooks.frappe.enqueue")
	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_authentic_callback_enqueues_processing_once(self, enabled_credential_sets, enqueue):
		enabled_credential_sets.return_value = [_credentials()]
		digest = _sign_processed(VALID_OBJ)

		_post({"obj": VALID_OBJ}, digest)

		enqueue.assert_called_once()
		kwargs = enqueue.call_args.kwargs
		self.assertEqual(kwargs["transaction"], "123456:Success")
		self.assertEqual(kwargs["job_id"], "paymob-process-123456:Success")
		self.assertTrue(kwargs["deduplicate"])

	@patch("paymob_integration.webhooks.frappe.enqueue")
	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_duplicate_delivery_does_not_enqueue(self, enabled_credential_sets, enqueue):
		enabled_credential_sets.return_value = [_credentials()]
		digest = _sign_processed(VALID_OBJ)

		_post({"obj": VALID_OBJ}, digest)
		enqueue.reset_mock()
		_post({"obj": VALID_OBJ}, digest)

		enqueue.assert_not_called()

	@patch("paymob_integration.webhooks.frappe.enqueue")
	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_refused_callback_does_not_enqueue(self, enabled_credential_sets, enqueue):
		enabled_credential_sets.return_value = [_credentials(secret="other_secret")]
		digest = _sign_processed(VALID_OBJ)

		_post({"obj": VALID_OBJ}, digest)

		enqueue.assert_not_called()

	@patch("paymob_integration.webhooks.settings.enabled_credential_sets")
	def test_persist_failure_raises_and_stores_nothing(self, enabled_credential_sets):
		enabled_credential_sets.return_value = [_credentials()]
		digest = _sign_processed(VALID_OBJ)

		with patch("frappe.model.document.Document.insert", side_effect=frappe.ValidationError):
			with self.assertRaises(frappe.ValidationError):
				_post({"obj": VALID_OBJ}, digest)

		self.assertEqual(frappe.db.count("Paymob Transaction", {"paymob_transaction_id": VALID_OBJ["id"]}), 0)
