"""Verifies Paymob's two callback signatures: the response callback (browser redirect, display
integrity only) and the processed callback (server-to-server webhook, ledger authority — Phase 05
onward gates a Payment Entry on `verify_processed_callback`).
"""

import hashlib
import hmac

# Paymob's fixed, documented order for the response callback. A missing field reads as "" —
# dropping a field from this list changes the digest and fails closed, it never widens what
# passes.
RESPONSE_CALLBACK_FIELDS = [
	"amount_cents",
	"created_at",
	"currency",
	"error_occured",
	"has_parent_transaction",
	"id",
	"integration_id",
	"is_3d_secure",
	"is_auth",
	"is_capture",
	"is_refunded",
	"is_standalone_payment",
	"is_voided",
	"order",
	"owner",
	"pending",
	"source_data.pan",
	"source_data.sub_type",
	"source_data.type",
	"success",
]

# Same field set as the response callback except `order` becomes `order.id` — the processed
# callback nests the order under `obj.order`, keyed by real JSON types (booleans, ints), not
# pre-stringified query params.
PROCESSED_CALLBACK_FIELDS = [
	"amount_cents",
	"created_at",
	"currency",
	"error_occured",
	"has_parent_transaction",
	"id",
	"integration_id",
	"is_3d_secure",
	"is_auth",
	"is_capture",
	"is_refunded",
	"is_standalone_payment",
	"is_voided",
	"order.id",
	"owner",
	"pending",
	"source_data.pan",
	"source_data.sub_type",
	"source_data.type",
	"success",
]


def verify_response_callback(params, secret):
	"""True only if params["hmac"] matches HMAC-SHA512 of the fixed field order.

	`params` values are read raw — Paymob sends "true"/"false" as strings, never coerced to
	bool, because the digest is computed over the exact bytes Paymob sent.
	"""
	received = params.get("hmac")
	values = [_read(params, field) for field in RESPONSE_CALLBACK_FIELDS]
	return _matches(values, received, secret)


def verify_processed_callback(obj, received, secret):
	"""True only if `received` matches HMAC-SHA512 of the processed callback's field order,
	dug out of the nested `obj` and rendered the way Paymob's signer renders JSON values.
	"""
	values = [_render(_dig(obj, field)) for field in PROCESSED_CALLBACK_FIELDS]
	return _matches(values, received, secret)


def _matches(values, received, secret):
	if not received:
		return False
	expected = hmac.new(secret.encode(), "".join(values).encode(), hashlib.sha512).hexdigest()
	try:
		return hmac.compare_digest(expected, received)
	except TypeError:
		# compare_digest raises TypeError for a non-ASCII str operand. Attacker-controlled
		# input must fail closed here, not bubble into an unhandled 500 on a guest endpoint.
		return False


def _read(params, field):
	if field == "order":
		# ponytail: docs disagree whether the redirect sends `order` or `order_id`; accept
		# both until one sandbox payment settles it. DoD carries the task to record the
		# real answer in docs/reference/endpoints.md and delete the losing branch here.
		return str(params.get("order", params.get("order_id", "")))
	return str(params.get(field, ""))


def _dig(obj, path):
	"""Walk a dotted path (e.g. "source_data.pan") through nested dicts. Returns None the
	moment a level is not a dict, so a non-dict `obj` yields None for every field and fails
	closed rather than raising.
	"""
	value = obj
	for key in path.split("."):
		if not isinstance(value, dict):
			return None
		value = value.get(key)
	return value


def _render(value):
	"""Render one dug-out JSON value into the string Paymob's signer hashed: lowercase JSON
	booleans, empty string for a missing/None value, plain `str()` otherwise. `bool` is checked
	before any numeric case because `isinstance(True, int)` is `True`.
	"""
	if isinstance(value, bool):
		return "true" if value else "false"
	if value is None:
		return ""
	return str(value)
