"""Verifies Paymob's response callback (the browser redirect). Display integrity only — this
signature never gates a ledger write; the processed callback in Phase 04 has its own field list.
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


def verify_response_callback(params, secret):
	"""True only if params["hmac"] matches HMAC-SHA512 of the fixed field order.

	`params` values are read raw — Paymob sends "true"/"false" as strings, never coerced to
	bool, because the digest is computed over the exact bytes Paymob sent.
	"""
	received = params.get("hmac")
	if not received:
		return False

	message = "".join(_read(params, field) for field in RESPONSE_CALLBACK_FIELDS)
	expected = hmac.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()
	return hmac.compare_digest(expected, received)


def _read(params, field):
	if field == "order":
		# ponytail: docs disagree whether the redirect sends `order` or `order_id`; accept
		# both until one sandbox payment settles it. DoD carries the task to record the
		# real answer in docs/reference/endpoints.md and delete the losing branch here.
		return str(params.get("order", params.get("order_id", "")))
	return str(params.get(field, ""))
