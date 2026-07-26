"""Endpoint tests for the processed callback, driven through a real werkzeug request so the
frappe.form_dict / request.args split (the make_form_dict landmine, see webhooks.py) is actually
exercised rather than assumed.
"""

from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from paymob_integration import webhooks
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


class TestProcessedCallback(UnitTestCase):
	def setUp(self):
		frappe.local.response = frappe._dict()

	def tearDown(self):
		frappe.local.request = None

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
