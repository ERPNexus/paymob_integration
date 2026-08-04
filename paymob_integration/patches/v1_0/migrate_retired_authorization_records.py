"""Make records from the retired authorization workflow safe on upgraded sites."""

import frappe

from paymob_integration.paymob import transactions


def execute():
	for attempt in frappe.get_all(
		"Paymob Payment Attempt", filters={"state": ["in", ["Authorized", "Voided"]]}, pluck="name"
	):
		state = frappe.db.get_value("Paymob Payment Attempt", attempt, "state")
		frappe.db.set_value(
			"Paymob Payment Attempt",
			attempt,
			{"state": "Pending" if state == "Authorized" else "Failed", "needs_human_attention": 1},
			update_modified=False,
		)

	for row in frappe.get_all(
		"Paymob Transaction",
		filters={"event_kind": ["in", ["Auth", "Capture", "Void"]]},
		fields=["name", "paymob_transaction_id", "event_kind", "attempt"],
	):
		subtype = row.event_kind
		new_name = transactions.event_key(row.paymob_transaction_id, "Unsupported", unsupported_subtype=subtype)
		frappe.db.set_value("Paymob Transaction", row.name, {"event_kind": "Unsupported", "processed": 0})
		if row.name != new_name:
			frappe.rename_doc("Paymob Transaction", row.name, new_name, force=True)
		if row.attempt:
			frappe.db.set_value(
				"Paymob Payment Attempt", row.attempt, "needs_human_attention", 1, update_modified=False
			)
