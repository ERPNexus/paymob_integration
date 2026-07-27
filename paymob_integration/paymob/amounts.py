"""Convert ERPNext amounts to Paymob integer minor units."""

from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe import _

MINOR_UNITS = {"EGP": 2, "SAR": 2, "AED": 2, "OMR": 3}


def to_minor_units(amount, currency):
	"""Convert an ERPNext amount to the integer Paymob expects."""
	exponent = _exponent(currency)
	quantised = Decimal(str(amount)).quantize(Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_UP)
	return int(quantised.scaleb(exponent))


def from_minor_units(cents, currency):
	"""Convert a Paymob integer back to an ERPNext amount."""
	return Decimal(int(cents)).scaleb(-_exponent(currency))


def amounts_match(expected_cents, expected_currency, received_cents, received_currency):
	"""An overpayment is a mismatch, not a bonus — and so is the right number in the wrong currency."""
	if int(expected_cents) != int(received_cents):
		return False
	return str(expected_currency or "").strip().upper() == str(received_currency or "").strip().upper()


def _exponent(currency):
	if currency not in MINOR_UNITS:
		frappe.throw(_("Paymob does not support the currency {0}.").format(currency))
	return MINOR_UNITS[currency]
