"""The executable form of docs/reference/states.md. Change both together."""

import frappe
from frappe import _


class IllegalTransition(frappe.ValidationError):
	pass


# docs/reference/states.md — anything not listed here raises.
LEGAL = {
	"Pending": {"Paid", "Failed", "Expired"},
	"Paid": {"Refunded"},
	"Failed": set(),
	"Expired": set(),
	"Refunded": set(),
}

# Auth / Capture / Void are deliberately absent — states.md has no `voided` state yet and the
# auth/capture flow ships in Phase 11.
EVENT_TARGET = {
	"Success": "Paid",
	"Decline": "Failed",
	"Refund": "Refunded",
}


def target_state(event_kind):
	return EVENT_TARGET.get(event_kind)


def check(current, target):
	"""True if the attempt must move, False if it is already there. Raises otherwise.

	A second, distinct Success (different transaction id) on an already-Paid attempt also lands
	on the `current == target` no-op — that is the duplicate-payment case Phase 09 guards and
	turns into its own audit entry; it is not an illegal transition here.
	"""
	if current == target:
		return False
	if target not in LEGAL.get(current, set()):
		frappe.throw(
			_("A Paymob payment cannot move from {0} to {1}.").format(_(current), _(target)),
			exc=IllegalTransition,
		)
	return True
