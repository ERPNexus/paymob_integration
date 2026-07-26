import hashlib
import hmac as hmac_lib

from frappe.tests import UnitTestCase

from paymob_integration.paymob.hmac_verify import RESPONSE_CALLBACK_FIELDS, verify_response_callback

SECRET = "hmac_test_FAKE_secret"

VALID_PARAMS = {
	"amount_cents": "27555",
	"created_at": "2026-07-26T10:00:00.000000",
	"currency": "EGP",
	"error_occured": "false",
	"has_parent_transaction": "false",
	"id": "123456",
	"integration_id": "1234",
	"is_3d_secure": "true",
	"is_auth": "false",
	"is_capture": "false",
	"is_refunded": "false",
	"is_standalone_payment": "true",
	"is_voided": "false",
	"order": "987654",
	"owner": "5555",
	"pending": "false",
	"source_data.pan": "1234",
	"source_data.sub_type": "MasterCard",
	"source_data.type": "card",
	"success": "true",
}


def _sign(params, secret=SECRET):
	"""Build the same concatenation the verifier is expected to build, independently of it."""
	order_value = params.get("order", params.get("order_id", ""))
	values = {**params, "order": order_value}
	message = "".join(str(values.get(field, "")) for field in RESPONSE_CALLBACK_FIELDS)
	digest = hmac_lib.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()
	return {**params, "hmac": digest}


class TestVerifyResponseCallback(UnitTestCase):
	def test_valid_signature_passes(self):
		self.assertTrue(verify_response_callback(_sign(VALID_PARAMS), SECRET))

	def test_tampered_field_is_rejected(self):
		params = _sign(VALID_PARAMS)
		params["success"] = "false"  # tamper after signing
		self.assertFalse(verify_response_callback(params, SECRET))

	def test_missing_hmac_is_rejected(self):
		self.assertFalse(verify_response_callback(dict(VALID_PARAMS), SECRET))

	def test_unrelated_extra_param_is_ignored(self):
		params = _sign(VALID_PARAMS)
		params["utm_source"] = "email"
		self.assertTrue(verify_response_callback(params, SECRET))

	def test_order_id_alias_is_accepted(self):
		params = dict(VALID_PARAMS)
		del params["order"]
		params["order_id"] = "987654"
		self.assertTrue(verify_response_callback(_sign(params), SECRET))
