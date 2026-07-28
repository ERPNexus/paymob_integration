"""One-shot Paymob refund and void requests; callbacks remain ledger authority."""

from paymob_integration.paymob import auth, client, settings

REFUND_PATH = "/api/acceptance/void_refund/refund"
VOID_PATH = "/api/acceptance/void_refund/void"


def refund(credentials, *, transaction_id, amount_cents):
	"""Make one refund request. Never retry: a lost response may still mean it succeeded."""
	return _post(
		credentials,
		REFUND_PATH,
		{"transaction_id": transaction_id, "amount_cents": int(amount_cents)},
	)


def void(credentials, *, transaction_id):
	"""Make one void request. Never retry: a lost response may still mean it succeeded."""
	return _post(credentials, VOID_PATH, {"transaction_id": transaction_id})


def _post(credentials, path, body):
	# ponytail: Accept's documented legacy convention puts the token in this body; switch this one
	# helper to an Authorization header if the sandbox measurement proves otherwise.
	return client.request(
		"POST",
		f"{settings.base_url(credentials)}{path}",
		json_body={"auth_token": auth.get_auth_token(credentials), **body},
	)
