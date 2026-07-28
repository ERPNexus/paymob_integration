"""The one function that creates a Paymob Audit Entry — grepping for "who creates an audit
entry" should return this function alone (rules/audit-trail.md, ADR-0009). Extracted from
`processor._audit` (Phase 09) so `ledger.py` can call it too without importing `processor`
(`processor` already imports `ledger`, so the reverse import would be circular).
"""

import frappe


def record(txn, attempt, event, needs_action, description, actor, **amounts_fields):
	"""`txn` is None only for an event with no Paymob transaction behind it — an expiry, where
	the absence is the whole point.
	"""
	entry = frappe.get_doc(
		{
			"doctype": "Paymob Audit Entry",
			"payment_request": attempt.payment_request if attempt else txn.payment_request,
			"attempt": attempt.name if attempt else None,
			"paymob_transaction_id": txn.paymob_transaction_id if txn else None,
			"paymob_transaction": txn.name if txn else None,
			"event": event,
			"description": description,
			"actor": actor,
			"occurred_at": (txn.received_at if txn else None) or frappe.utils.now_datetime(),
			"needs_action": needs_action,
			**amounts_fields,
		}
	)
	entry.insert(ignore_permissions=True)
	entry.submit()
	return entry
