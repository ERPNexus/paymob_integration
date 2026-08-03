"""Create a Paymob Intention once per payment attempt; never retry it automatically."""

from paymob_integration.paymob import client, settings


def create_intention(
	credentials,
	*,
	amount_cents,
	currency,
	special_reference,
	billing_data,
	items,
	notification_url,
	redirection_url,
	expiration,
	integration_ids,
):
	"""Create an intention and return the identifiers needed to continue checkout."""
	response = client.request(
		"POST",
		f"{settings.base_url(credentials)}/v1/intention/",
		headers={"Authorization": f"Token {credentials.get_password('secret_key')}"},
		json_body={
			"amount": int(amount_cents),
			"currency": currency,
			"payment_methods": [int(integration_id) for integration_id in integration_ids],
			"items": items,
			"billing_data": billing_data,
			"special_reference": special_reference,
			"notification_url": notification_url,
			"redirection_url": redirection_url,
			"expiration": int(expiration),
		},
	)
	return {
		"intention_id": str(response["id"]),
		"order_id": str(response["intention_order_id"]),
		"client_secret": response["client_secret"],
	}
