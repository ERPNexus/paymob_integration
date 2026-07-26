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
