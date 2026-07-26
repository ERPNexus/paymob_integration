"""Read Paymob Settings. No other module opens that doctype directly."""

import frappe
from frappe import _


def get_settings():
	return frappe.get_cached_doc("Paymob Settings")


def get_credential_set(country, currency, mode=None):
	"""Return the enabled credential set for a country and currency in `mode`.

	`mode` defaults to the site's current mode. Pass the attempt's own stored `mode` when
	re-verifying an existing attempt — the settings mode may have changed since checkout started.
	"""
	config = get_settings()
	if not config.enabled:
		frappe.throw(_("Paymob is not enabled. Ask an administrator to configure Paymob Settings."))

	mode = mode or config.mode
	for row in config.credential_sets:
		if row.enabled and row.country == country and row.currency == currency and row.mode == mode:
			return row

	frappe.throw(
		_("No Paymob credentials are configured for {0}, {1} in {2} mode.").format(country, currency, mode)
	)


def enabled_credential_sets():
	"""Every enabled credential row. Callers that must not let a payload pick the secret
	trial-verify against all of them rather than filtering on a claimed country or currency.
	Returns [] rather than throwing when Paymob is disabled — the webhook has no user to show
	a message to.
	"""
	config = get_settings()
	if not config.enabled:
		return []
	return [row for row in config.credential_sets if row.enabled]


def get_integration_ids(country, currency):
	"""Return enabled integration IDs for a country and currency in the site's current mode."""
	config = get_settings()
	return [
		row.integration_id
		for row in config.integration_ids
		if row.enabled and row.country == country and row.currency == currency and row.mode == config.mode
	]


def base_url(credentials):
	return credentials.base_url.rstrip("/")
