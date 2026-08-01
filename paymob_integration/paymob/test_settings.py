from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from paymob_integration.paymob import settings


class TestCredentialLookup(FrappeTestCase):
	@patch("paymob_integration.paymob.settings.get_settings")
	def test_includes_country(self, get_settings):
		egypt = frappe._dict(country="Egypt", currency="USD", mode="Test", enabled=1)
		saudi_arabia = frappe._dict(country="Saudi Arabia", currency="USD", mode="Test", enabled=1)
		get_settings.return_value = frappe._dict(
			enabled=1, mode="Test", credential_sets=[saudi_arabia, egypt]
		)

		self.assertIs(settings.get_credential_set("Egypt", "USD"), egypt)

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_explicit_mode_overrides_site_mode(self, get_settings):
		test_row = frappe._dict(country="Egypt", currency="USD", mode="Test", enabled=1)
		live_row = frappe._dict(country="Egypt", currency="USD", mode="Live", enabled=1)
		get_settings.return_value = frappe._dict(enabled=1, mode="Live", credential_sets=[test_row, live_row])

		self.assertIs(settings.get_credential_set("Egypt", "USD", "Test"), test_row)


class TestEnabledCredentialSets(FrappeTestCase):
	@patch("paymob_integration.paymob.settings.get_settings")
	def test_disabled_returns_empty(self, get_settings):
		get_settings.return_value = frappe._dict(enabled=0, credential_sets=[frappe._dict(enabled=1)])

		self.assertEqual(settings.enabled_credential_sets(), [])


class TestIntegrationIds(FrappeTestCase):
	@patch("paymob_integration.paymob.settings.get_settings")
	def test_capture_mode_does_not_filter_integration_ids(self, get_settings):
		"""With no `capture_mode` argument (today's every caller except an authorize-only
		checkout), `capture_mode` never gates which integration IDs come back — callback flags
		alone decide attempt state (ADR-0022).
		"""
		auto_capture = frappe._dict(
			enabled=1,
			country="Egypt",
			currency="EGP",
			mode="Test",
			capture_mode="Auto Capture",
			integration_id="1001",
		)
		authorize_only = frappe._dict(
			enabled=1,
			country="Egypt",
			currency="EGP",
			mode="Test",
			capture_mode="Authorize Only",
			integration_id="1002",
		)
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[auto_capture, authorize_only])

		self.assertEqual(settings.get_integration_ids("Egypt", "EGP"), ["1001", "1002"])

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_authorize_only_filters_to_the_auth_row(self, get_settings):
		auto_capture = frappe._dict(
			enabled=1,
			country="Egypt",
			currency="EGP",
			mode="Test",
			capture_mode="Auto Capture",
			integration_id="1001",
		)
		authorize_only = frappe._dict(
			enabled=1,
			country="Egypt",
			currency="EGP",
			mode="Test",
			capture_mode="Authorize Only",
			integration_id="1002",
		)
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[auto_capture, authorize_only])

		self.assertEqual(settings.get_integration_ids("Egypt", "EGP", "Authorize Only"), ["1002"])

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_authorize_only_with_no_matching_row_throws(self, get_settings):
		auto_capture = frappe._dict(
			enabled=1,
			country="Egypt",
			currency="EGP",
			mode="Test",
			capture_mode="Auto Capture",
			integration_id="1001",
		)
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[auto_capture])

		with self.assertRaisesRegex(frappe.ValidationError, "Egypt, EGP"):
			settings.get_integration_ids("Egypt", "EGP", "Authorize Only")
