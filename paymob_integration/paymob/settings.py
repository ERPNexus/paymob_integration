"""Read Paymob Settings. No other module opens that doctype directly."""

import frappe
from frappe import _


def get_settings():
	return frappe.get_cached_doc("Paymob Settings")


def is_enabled(config=None, *, throw=False):
	enabled = bool((config or get_settings()).enabled)
	if throw and not enabled:
		frappe.throw(_("Paymob is not enabled. Ask an administrator to configure Paymob Settings."))
	return enabled


def _pick(rows, company, mode, default_mode):
	"""Multi-company: a company with rows of its own uses only those, in their own mode (each
	seller has its own Paymob account and goes live on its own day). A company without rows uses
	the rows that name no company, in the site's mode. One company's row never serves another."""
	own = [row for row in rows if company and row.get("company") == company]
	if own:
		return [row for row in own if not mode or row.mode == mode]
	mode = mode or default_mode
	return [row for row in rows if not row.get("company") and row.mode == mode]


def get_credential_set(country, currency, mode=None, company=None):
	"""Return the enabled credential set for a country and currency, for `company`.

	`mode` defaults to the company's own row, else the site's mode. Pass the attempt's own stored
	`mode` when re-verifying an existing attempt — the mode may have changed since checkout started.
	"""
	config = get_settings()
	is_enabled(config, throw=True)

	rows = [row for row in config.credential_sets if row.enabled and row.country == country and row.currency == currency]
	for row in _pick(rows, company, mode, config.mode):
		return row

	frappe.throw(
		_("No Paymob credentials are configured for {0}, {1} in {2} mode.").format(
			country, currency, mode or config.mode
		)
	)


def enabled_credential_sets():
	"""Every enabled credential row. Callers that must not let a payload pick the secret
	trial-verify against all of them rather than filtering on a claimed country or currency.
	Returns [] rather than throwing when Paymob is disabled — the webhook has no user to show
	a message to.
	"""
	config = get_settings()
	if not is_enabled(config):
		return []
	return [row for row in config.credential_sets if row.enabled]


def resolve_integrations(country, currency, company=None, mode=None):
	"""Return enabled Integration IDs for a country and currency, for `company` in `mode`."""
	config = get_settings()
	is_enabled(config, throw=True)
	rows = [row for row in config.integration_ids if row.enabled and row.country == country and row.currency == currency]
	rows = _pick(rows, company, mode, config.mode)
	if not rows:
		frappe.throw(
			_("No enabled Paymob Integration ID is configured for {0}, {1} in {2} mode.").format(
				country, currency, mode or config.mode
			)
		)
	return [row.integration_id for row in rows]


def base_url(credentials):
	return credentials.base_url.rstrip("/")


def attempt_company(attempt):
	"""An attempt is verified with the credentials of the company its request belongs to."""
	return frappe.db.get_value("Payment Request", attempt.payment_request, "company")
