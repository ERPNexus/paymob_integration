# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from paymob_integration.paymob import auth, client, settings


class PaymobSettings(Document):
	pass


@frappe.whitelist()
def test_connection(country, currency):
	"""Prove the configured API key authenticates against Paymob."""
	frappe.only_for("System Manager")
	credentials = settings.get_credential_set(country, currency)
	try:
		auth.get_auth_token(credentials, force_refresh=True)
	except client.PaymobError as exc:
		frappe.throw(str(exc))
	frappe.logger("paymob").info(f"test_connection ok country={credentials.country} mode={credentials.mode}")
	return {
		"ok": True,
		"message": _("Connected to Paymob for {0} in {1} mode.").format(
			credentials.country, credentials.mode
		),
	}
