"""Read Paymob Settings. No other module opens that doctype directly."""

import frappe
from frappe import _


def get_settings():
	return frappe.get_cached_doc("Paymob Settings")


def get_credential_set(country, currency):
	"""Return the enabled credential set for a country and currency in the site's current mode."""
	config = get_settings()
	if not config.enabled:
		frappe.throw(_("Paymob is not enabled. Ask an administrator to configure Paymob Settings."))

	for row in config.credential_sets:
		if row.enabled and row.country == country and row.currency == currency and row.mode == config.mode:
			return row

	frappe.throw(
		_("No Paymob credentials are configured for {0}, {1} in {2} mode.").format(
			country, currency, config.mode
		)
	)


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
