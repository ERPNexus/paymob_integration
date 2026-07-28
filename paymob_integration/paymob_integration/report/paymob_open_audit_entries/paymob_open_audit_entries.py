"""The "needs action" view rules/audit-trail.md requires — a list filter cannot express "has no
superseding record", so this is a Script Report doing a four-line anti-join instead of raw SQL.
"""

import frappe
from frappe import _


def execute(filters=None):
	superseded = {
		row.supersedes
		for row in frappe.get_all(
			"Paymob Audit Entry",
			filters={"supersedes": ["is", "set"], "docstatus": 1},
			fields=["supersedes"],
		)
	}
	rows = frappe.get_all(
		"Paymob Audit Entry",
		filters={"needs_action": 1, "docstatus": 1},
		fields=[
			"name",
			"occurred_at",
			"event",
			"payment_request",
			"attempt",
			"paymob_transaction_id",
			"expected_amount_cents",
			"received_amount_cents",
			"description",
		],
		order_by="occurred_at desc",
	)
	return _columns(), [row for row in rows if row.name not in superseded]


def _columns():
	return [
		{
			"label": _("Audit Entry"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Paymob Audit Entry",
			"width": 160,
		},
		{"label": _("Occurred At"), "fieldname": "occurred_at", "fieldtype": "Datetime", "width": 160},
		{"label": _("Event"), "fieldname": "event", "fieldtype": "Data", "width": 140},
		{
			"label": _("Payment Request"),
			"fieldname": "payment_request",
			"fieldtype": "Link",
			"options": "Payment Request",
			"width": 140,
		},
		{
			"label": _("Attempt"),
			"fieldname": "attempt",
			"fieldtype": "Link",
			"options": "Paymob Payment Attempt",
			"width": 140,
		},
		{
			"label": _("Paymob Transaction ID"),
			"fieldname": "paymob_transaction_id",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Expected Amount Cents"),
			"fieldname": "expected_amount_cents",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": _("Received Amount Cents"),
			"fieldname": "received_amount_cents",
			"fieldtype": "Int",
			"width": 140,
		},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 300},
	]
