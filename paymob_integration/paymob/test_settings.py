from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from paymob_integration import api
from paymob_integration.paymob import settings


def _row(country="Egypt", currency="EGP", mode="Test", integration_id="1001", enabled=1):
	return frappe._dict(
		enabled=enabled, country=country, currency=currency, mode=mode, integration_id=integration_id
	)


class TestEnabledStatus(FrappeTestCase):
	@patch("paymob_integration.api.settings.is_enabled", return_value=False)
	def test_returns_only_the_enabled_flag(self, is_enabled):
		self.assertEqual(api.get_enabled_status(), {"enabled": False})
		is_enabled.assert_called_once_with()


class TestResolveIntegrations(FrappeTestCase):
	@patch("paymob_integration.paymob.settings.get_settings")
	def test_returns_all_enabled_ids_for_country_currency_and_mode(self, get_settings):
		get_settings.return_value = frappe._dict(
			enabled=1, mode="Test", integration_ids=[_row(integration_id="1001"), _row(integration_id="1004")]
		)
		self.assertEqual(settings.resolve_integrations("Egypt", "EGP"), ["1001", "1004"])

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_excludes_disabled_and_other_mode_rows(self, get_settings):
		get_settings.return_value = frappe._dict(
			enabled=1,
			mode="Test",
			integration_ids=[
				_row(integration_id="1001", enabled=0),
				_row(integration_id="1002", mode="Live"),
			],
		)
		with self.assertRaises(frappe.ValidationError):
			settings.resolve_integrations("Egypt", "EGP")


class TestCompanyCredentials(FrappeTestCase):
	"""Multi-company: each seller's own Paymob account, never another's."""

	def _settings(self, *rows):
		return frappe._dict(enabled=1, mode="Live", credential_sets=list(rows))

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_a_company_uses_its_own_row_in_its_own_mode(self, get_settings):
		own = frappe._dict(_row(mode="Test"), company="A", name="own")
		shared = frappe._dict(_row(mode="Live"), company=None, name="shared")
		get_settings.return_value = self._settings(shared, own)
		self.assertEqual(settings.get_credential_set("Egypt", "EGP", company="A").name, "own")
		self.assertEqual(settings.get_credential_set("Egypt", "EGP", company="B").name, "shared")

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_one_companys_row_never_serves_another(self, get_settings):
		get_settings.return_value = self._settings(frappe._dict(_row(mode="Live"), company="A", name="own"))
		with self.assertRaises(frappe.ValidationError):
			settings.get_credential_set("Egypt", "EGP", company="B")
