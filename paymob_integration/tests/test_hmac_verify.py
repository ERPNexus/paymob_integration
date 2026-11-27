import hashlib
import hmac as hmac_lib

from frappe.tests.utils import FrappeTestCase

from paymob_integration.paymob.hmac_verify import (
	PROCESSED_CALLBACK_FIELDS,
	RESPONSE_CALLBACK_FIELDS,
	verify_processed_callback,
	verify_response_callback,
)

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


class TestVerifyResponseCallback(FrappeTestCase):
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

	def test_non_ascii_hmac_is_rejected_not_raised(self):
		params = {**_sign(VALID_PARAMS), "hmac": "é"}
		self.assertFalse(verify_response_callback(params, SECRET))


# Native Python types (real bools, real ints) — this is what orjson.loads hands us for the
# processed callback's nested `obj`, unlike the response callback's flat, pre-stringified params.
VALID_OBJ = {
	"amount_cents": 27555,
	"created_at": "2026-07-26T10:00:00.000000",
	"currency": "EGP",
	"error_occured": False,
	"has_parent_transaction": False,
	"id": 123456,
	"integration_id": 1234,
	"is_3d_secure": True,
	"is_auth": False,
	"is_capture": False,
	"is_refunded": False,
	"is_standalone_payment": True,
	"is_voided": False,
	"order": {"id": 987654, "merchant_order_id": "PR-00042-1"},
	"owner": 5555,
	"pending": False,
	"source_data": {"pan": "1234", "sub_type": "MasterCard", "type": "card"},
	"success": True,
}


def _dig(obj, path):
	"""Independent of hmac_verify._dig — walks the same dotted paths."""
	value = obj
	for key in path.split("."):
		if not isinstance(value, dict):
			return None
		value = value.get(key)
	return value


def _render(value):
	"""Independent of hmac_verify._render — the reference rendering this signer is expected
	to match: lowercase JSON booleans, "" for a missing value, plain str() otherwise.
	"""
	if isinstance(value, bool):
		return "true" if value else "false"
	if value is None:
		return ""
	return str(value)


def _sign_processed(obj, secret=SECRET):
	"""Build the same concatenation the verifier is expected to build, independently of it."""
	message = "".join(_render(_dig(obj, field)) for field in PROCESSED_CALLBACK_FIELDS)
	return hmac_lib.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()


class TestVerifyProcessedCallback(FrappeTestCase):
	def test_valid_signature_passes(self):
		digest = _sign_processed(VALID_OBJ)
		self.assertTrue(verify_processed_callback(VALID_OBJ, digest, SECRET))

	def test_wrong_secret_is_rejected(self):
		digest = _sign_processed(VALID_OBJ)
		self.assertFalse(verify_processed_callback(VALID_OBJ, digest, "other_secret"))

	def test_tampered_field_is_rejected(self):
		digest = _sign_processed(VALID_OBJ)
		obj = {**VALID_OBJ, "success": False}
		self.assertFalse(verify_processed_callback(obj, digest, SECRET))

	def test_missing_hmac_is_rejected(self):
		self.assertFalse(verify_processed_callback(VALID_OBJ, None, SECRET))

	def test_empty_hmac_is_rejected(self):
		self.assertFalse(verify_processed_callback(VALID_OBJ, "", SECRET))

	def test_key_order_does_not_matter(self):
		digest = _sign_processed(VALID_OBJ)
		reordered = dict(reversed(list(VALID_OBJ.items())))
		self.assertTrue(verify_processed_callback(reordered, digest, SECRET))

	def test_booleans_render_lowercase(self):
		message = "".join(_render(_dig(VALID_OBJ, field)) for field in PROCESSED_CALLBACK_FIELDS)
		self.assertIn("true", message)
		self.assertNotIn("True", message)
		digest = hmac_lib.new(SECRET.encode(), message.encode(), hashlib.sha512).hexdigest()
		self.assertTrue(verify_processed_callback(VALID_OBJ, digest, SECRET))

	def test_order_id_not_order_dict(self):
		digest = _sign_processed(VALID_OBJ)
		obj = {**VALID_OBJ, "order": {**VALID_OBJ["order"], "id": 999999}}
		self.assertFalse(verify_processed_callback(obj, digest, SECRET))

	def test_missing_nested_branch_renders_empty_without_raising(self):
		obj = {key: value for key, value in VALID_OBJ.items() if key != "source_data"}
		digest = _sign_processed(obj)
		self.assertTrue(verify_processed_callback(obj, digest, SECRET))

	def test_non_ascii_hmac_is_rejected_not_raised(self):
		self.assertFalse(verify_processed_callback(VALID_OBJ, "é", SECRET))
