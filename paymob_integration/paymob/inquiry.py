"""Transaction Inquiry by merchant reference. The Phase 10 poller and the refund path
(`processor.process_transaction`) both need to ask Paymob what actually happened to a
reference; this is the one place that does it, so both share one retry policy.
"""

from paymob_integration.paymob import auth, client, settings

INQUIRY_PATH = "/api/ecommerce/orders/transaction_inquiry"


def by_reference(credentials, special_reference):
	"""Retries exactly once, on a 401 only. A timeout or 5xx propagates straight out to the
	caller; a repeated 401 is not retried again (rules/implementation-gate.md §11).
	"""
	try:
		return _post_inquiry(credentials, special_reference, force_refresh=False)
	except client.PaymobAPIError as exc:
		if exc.status_code == 404:
			return None  # Paymob has no transaction for this reference
		if exc.status_code != 401:
			raise  # 5xx / anything else: the caller decides what happens next
	try:
		return _post_inquiry(credentials, special_reference, force_refresh=True)
	except client.PaymobAPIError as exc:
		if exc.status_code == 404:
			return None
		raise  # a second 401 is not retried again


def _post_inquiry(credentials, special_reference, force_refresh):
	token = auth.get_auth_token(credentials, force_refresh=force_refresh)
	url = f"{settings.base_url(credentials)}{INQUIRY_PATH}"
	return client.request(
		"POST",
		url,
		headers={"Authorization": f"Bearer {token}"},
		json_body={"merchant_order_id": special_reference},
	)
