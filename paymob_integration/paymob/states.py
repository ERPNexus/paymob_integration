"""The executable form of docs/reference/states.md. Change both together."""

import frappe
from frappe import _


class IllegalTransition(frappe.ValidationError):
	pass


# docs/reference/states.md — anything not listed here raises.
LEGAL = {
	"Pending": {"Paid", "Failed", "Expired"},
	"Paid": {"Partially Refunded", "Refunded"},
	"Partially Refunded": {"Refunded"},
	"Failed": {"Paid"},
	"Expired": set(),
	"Refunded": set(),
}

EVENT_TARGET = {
	"Success": "Paid",
	"Decline": "Failed",
}


def target_state(event_kind):
	return EVENT_TARGET.get(event_kind)


def refund_target(refunded_total_cents, expected_amount_cents):
	"""Choose the state for a local, integer-cents refund total."""
	return "Refunded" if refunded_total_cents >= expected_amount_cents else "Partially Refunded"


def check(current, target):
	"""True if the attempt must move, False if it is already there. Raises otherwise.

	A second, distinct Success (different transaction id) on an already-Paid attempt and a second
	partial refund both land on the `current == target` no-op. Their callers own the respective
	duplicate and delta handling; this function only decides whether the state itself moves.
	"""
	if current == target:
		return False
	if target not in LEGAL.get(current, set()):
		frappe.throw(
			_("A Paymob payment cannot move from {0} to {1}.").format(_(current), _(target)),
			exc=IllegalTransition,
		)
	return True
