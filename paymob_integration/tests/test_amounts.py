from decimal import Decimal

import frappe
from frappe.tests import UnitTestCase

from paymob_integration.paymob import amounts


class TestMinorUnits(UnitTestCase):
	def test_two_decimal_currency(self):
		self.assertEqual(amounts.to_minor_units("275.55", "EGP"), 27555)

	def test_decimal_arithmetic_is_exact(self):
		self.assertEqual(amounts.to_minor_units(Decimal("0.1") + Decimal("0.2"), "EGP"), 30)

	def test_three_decimal_currency(self):
		self.assertEqual(amounts.to_minor_units("1.234", "OMR"), 1234)

	def test_half_a_minor_unit_rounds_up(self):
		self.assertEqual(amounts.to_minor_units("1.005", "EGP"), 101)

	def test_unsupported_currency_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			amounts.to_minor_units("10.00", "JPY")

	def test_round_trip(self):
		self.assertEqual(amounts.from_minor_units(27555, "EGP"), Decimal("275.55"))

	def test_match_is_exact(self):
		self.assertTrue(amounts.amounts_match(27555, 27555))
		self.assertFalse(amounts.amounts_match(27555, 27554))
		self.assertFalse(amounts.amounts_match(27555, 27556))
