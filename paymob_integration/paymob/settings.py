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


def capture_mode_for(rows, country, currency, mode):
	"""The one capture mode a group of Integration IDs agrees on, or a throw.

	Shared by `Paymob Settings.validate` (refuse the save) and `resolve_integrations`
	(refuse the checkout).
	"""
	modes = {row.capture_mode or "Auto Capture" for row in rows}
	if len(modes) > 1:
		frappe.throw(
			_(
				"Paymob Integration IDs for {0}, {1} in {2} mode mix Auto Capture and "
				"Authorize Only. Every enabled integration for one country, currency and mode "
				"must use the same capture mode."
			).format(country, currency, mode),
			title=_("Mixed Capture Modes"),
		)
	return modes.pop()


def resolve_integrations(country, currency):
	"""Return (capture_mode, integration_ids) for a country and currency in the site's mode.

	Paymob Settings decides whether a checkout charges or holds — never the browser and never a
	field on the Payment Request. Every enabled row for the group is offered to the payer; they
	all settle the same way (ADR-0027).
	"""
	config = get_settings()
	rows = [
		row
		for row in config.integration_ids
		if row.enabled and row.country == country and row.currency == currency and row.mode == config.mode
	]
	if not rows:
		frappe.throw(
			_("No enabled Paymob Integration ID is configured for {0}, {1} in {2} mode.").format(
				country, currency, config.mode
			)
		)
	return capture_mode_for(rows, country, currency, config.mode), [row.integration_id for row in rows]


def base_url(credentials):
	return credentials.base_url.rstrip("/")
