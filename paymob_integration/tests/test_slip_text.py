"""The payer page shows a short invoice number and a readable date, never the raw document name."""

import frappe
from frappe.tests.utils import FrappeTestCase

from paymob_integration.slip import doc_number, friendly_date


class TestSlipText(FrappeTestCase):
	def test_doc_number_matches_the_apps(self):
		self.assertEqual(doc_number("ACC-SINV-2026-04258"), "4258")
		self.assertEqual(doc_number("ACC-SINV-2026-04258-1"), "4258")
		self.assertEqual(doc_number("SAL-ORD-2026-00012"), "12")
		self.assertEqual(doc_number("INV-7"), "7")
		self.assertIsNone(doc_number("ABC"))
		self.assertIsNone(doc_number(None))

	def test_friendly_date_in_arabic(self):
		frappe.local.lang = "ar"
		try:
			self.assertEqual(friendly_date("2026-11-22"), "الأحد 22 نوفمبر" if frappe.utils.getdate().year == 2026 else "الأحد 22 نوفمبر 2026")
		finally:
			frappe.local.lang = "en"
