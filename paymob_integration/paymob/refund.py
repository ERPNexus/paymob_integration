"""One-shot Paymob refund requests; signed callbacks remain ledger authority."""

from paymob_integration.paymob import auth, client, settings

REFUND_PATH = "/api/acceptance/void_refund/refund"


def request(credentials, *, transaction_id, amount_cents):
	"""Make one refund request. Never retry: a lost response may still mean it succeeded."""
	return client.request(
		"POST",
		f"{settings.base_url(credentials)}{REFUND_PATH}",
		json_body={
			"auth_token": auth.get_auth_token(credentials),
			"transaction_id": transaction_id,
			"amount_cents": int(amount_cents),
		},
	)
