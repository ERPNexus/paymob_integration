"""API key to Bearer auth token, used by Transaction Inquiry."""

import frappe

from paymob_integration.paymob import client, settings

TOKEN_TTL_SECONDS = 45 * 60


def cache_key(credentials):
	return f"paymob_auth_token:{credentials.country}:{credentials.currency}:{credentials.mode}"


def get_auth_token(credentials, force_refresh=False):
	key = cache_key(credentials)
	if not force_refresh:
		cached = frappe.cache().get_value(key)
		if cached:
			return cached

	response = client.request(
		"POST",
		f"{settings.base_url(credentials)}/api/auth/tokens",
		json_body={"api_key": credentials.get_password("api_key")},
	)
	token = response["token"]
	frappe.cache().set_value(key, token, expires_in_sec=TOKEN_TTL_SECONDS)
	return token
