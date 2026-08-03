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


def _row(
	country="Egypt",
	currency="EGP",
	mode="Test",
	capture_mode="Auto Capture",
	integration_id="1001",
	enabled=1,
):
	return frappe._dict(
		enabled=enabled,
		country=country,
		currency=currency,
		mode=mode,
		capture_mode=capture_mode,
		integration_id=integration_id,
	)


class TestResolveIntegrations(FrappeTestCase):
	@patch("paymob_integration.paymob.settings.get_settings")
	def test_uniform_auto_capture_group_returns_every_id(self, get_settings):
		card = _row(capture_mode="Auto Capture", integration_id="1001")
		wallet = _row(capture_mode="Auto Capture", integration_id="1004")
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[card, wallet])

		self.assertEqual(settings.resolve_integrations("Egypt", "EGP"), ("Auto Capture", ["1001", "1004"]))

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_uniform_authorize_only_group_returns_every_id(self, get_settings):
		card = _row(capture_mode="Authorize Only", integration_id="1002")
		wallet = _row(capture_mode="Authorize Only", integration_id="1003")
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[card, wallet])

		self.assertEqual(settings.resolve_integrations("Egypt", "EGP"), ("Authorize Only", ["1002", "1003"]))

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_mixed_group_throws(self, get_settings):
		auto_capture = _row(capture_mode="Auto Capture", integration_id="1001")
		authorize_only = _row(capture_mode="Authorize Only", integration_id="1002")
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[auto_capture, authorize_only])

		with self.assertRaisesRegex(frappe.ValidationError, "Authorize Only"):
			settings.resolve_integrations("Egypt", "EGP")

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_disabled_row_of_the_other_mode_is_ignored(self, get_settings):
		disabled_auto = _row(capture_mode="Auto Capture", integration_id="1001", enabled=0)
		authorize_only = _row(capture_mode="Authorize Only", integration_id="1002")
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[disabled_auto, authorize_only])

		self.assertEqual(settings.resolve_integrations("Egypt", "EGP"), ("Authorize Only", ["1002"]))

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_other_currency_may_use_the_other_mode(self, get_settings):
		egp_auth = _row(currency="EGP", capture_mode="Authorize Only", integration_id="1002")
		usd_auto = _row(currency="USD", capture_mode="Auto Capture", integration_id="2001")
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[egp_auth, usd_auto])

		self.assertEqual(settings.resolve_integrations("Egypt", "EGP"), ("Authorize Only", ["1002"]))
		self.assertEqual(settings.resolve_integrations("Egypt", "USD"), ("Auto Capture", ["2001"]))

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_wrong_site_mode_row_is_excluded(self, get_settings):
		live_row = _row(mode="Live", integration_id="9001")
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[live_row])

		with self.assertRaises(frappe.ValidationError):
			settings.resolve_integrations("Egypt", "EGP")

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_no_enabled_row_throws(self, get_settings):
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[])

		with self.assertRaisesRegex(frappe.ValidationError, "Egypt, EGP.*Test"):
			settings.resolve_integrations("Egypt", "EGP")

	@patch("paymob_integration.paymob.settings.get_settings")
	def test_blank_capture_mode_is_auto_capture(self, get_settings):
		blank = _row(capture_mode=None, integration_id="1001")
		get_settings.return_value = frappe._dict(mode="Test", integration_ids=[blank])

		self.assertEqual(settings.resolve_integrations("Egypt", "EGP"), ("Auto Capture", ["1001"]))
