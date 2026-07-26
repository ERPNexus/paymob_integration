"""Convert ERPNext amounts to Paymob integer minor units."""

from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe import _

MINOR_UNITS = {"EGP": 2, "SAR": 2, "AED": 2, "OMR": 3}


def to_minor_units(amount, currency):
	"""Convert an ERPNext amount to the integer Paymob expects."""
	exponent = _exponent(currency)
	quantised = Decimal(str(amount)).quantize(
		Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_UP
	)
	return int(quantised.scaleb(exponent))


def from_minor_units(cents, currency):
	"""Convert a Paymob integer back to an ERPNext amount."""
	return Decimal(int(cents)).scaleb(-_exponent(currency))


def amounts_match(expected_cents, received_cents):
	"""An overpayment is a mismatch, not a bonus."""
	return int(expected_cents) == int(received_cents)


def _exponent(currency):
	if currency not in MINOR_UNITS:
		frappe.throw(_("Paymob does not support the currency {0}.").format(currency))
	return MINOR_UNITS[currency]
