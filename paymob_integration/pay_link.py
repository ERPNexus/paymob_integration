"""Signed, app-owned Payment Request URLs for payer email."""

from frappe.utils import get_url
from frappe.utils.verified_command import get_signed_params


def build(payment_request: str) -> str:
	return f"{get_url()}/paymob-pay?{get_signed_params({'ref': payment_request})}"
