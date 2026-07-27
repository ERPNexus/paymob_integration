"""The single Payment Entry write path (rules/payments.md rule 1). Every caller — the webhook
processor now, the Phase 10 poller and Phase 11 refund path later — routes through
`post_payment`. Grepping for `create_payment_entry` should return one non-core call site: here.
"""

import frappe
from frappe import _

from paymob_integration.paymob import amounts, audit, settings

ACTOR = "paymob_integration.paymob.ledger.post_payment"


def post_payment(attempt, transaction):
	"""`attempt` must already be locked (`for_update=True`) by the caller before this runs. That
	lock is per-attempt, not per-Payment-Request — a retry is a *new* attempt (rules/payments.md),
	so two verified successes belonging to two different attempts of the same Payment Request can
	reach here concurrently. The row lock taken below on the Payment Request itself, before the
	duplicate lookup, is what actually serialises them: the second caller blocks until the first
	commits its Payment Entry, then sees it and is audited instead of posting a second one.

	A second genuine `Success` (a different transaction id) on an already-`Paid` attempt reaches
	here too — `states.check` treats `current == target` as a no-op, not an illegal transition
	(rules/payments.md rule 11). The guard is a lookup, not a second dedup: the Phase 05 unique
	constraint on the transaction's own name already rejects a *repeated* delivery of the same
	event before it ever reaches this function.
	"""
	payment_request = frappe.get_doc("Payment Request", attempt.payment_request, for_update=True)

	existing = frappe.db.get_value(
		"Payment Entry Reference",
		{"payment_request": attempt.payment_request, "docstatus": 1},
		"parent",
	)
	if existing:
		_audit_duplicate(attempt, transaction, existing)
		return None

	credentials = settings.get_credential_set(attempt.country, attempt.currency, attempt.mode)
	payment_request.payment_account = credentials.payment_account  # in-memory only, ADR-0008
	payment_entry = payment_request.create_payment_entry(submit=True)

	# ERPNext posts payment_request.outstanding_amount, read now — not attempt.expected_amount_cents,
	# a snapshot from intention creation already checked by Phase 07. The two can drift (a partial
	# cash payment, a credit note); this catches it, rolls back, and leaves the row for Phase 10.
	#
	# `paid_amount` is denominated in paid_from_account_currency (the party/company side) and
	# `received_amount` in paid_to_account_currency (the clearing account side, set above from the
	# Paymob credential set) — they differ whenever the Payment Request currency isn't company
	# currency. Compare against whichever one is actually in Paymob's currency, not paid_amount
	# unconditionally, or a correct foreign-currency payment reports a false mismatch and rolls back.
	if payment_entry.paid_to_account_currency == transaction.currency:
		entry_amount = payment_entry.received_amount
	elif payment_entry.paid_from_account_currency == transaction.currency:
		entry_amount = payment_entry.paid_amount
	else:
		frappe.throw(
			_("Payment Entry {0} has no side denominated in {1}.").format(
				payment_entry.name, transaction.currency
			)
		)

	posted = amounts.to_minor_units(entry_amount, transaction.currency)
	if posted != transaction.amount_cents:
		frappe.throw(
			_("Posted amount {0} does not match the confirmed payment amount {1}.").format(
				posted, transaction.amount_cents
			)
		)

	attempt.payment_entry = payment_entry.name
	attempt.save(ignore_permissions=True)
	frappe.logger("paymob").info(
		f"payment entry posted payment_request={attempt.payment_request} attempt={attempt.name} "
		f"txn={transaction.paymob_transaction_id} payment_entry={payment_entry.name}"
	)
	return payment_entry.name


def _audit_duplicate(attempt, transaction, existing_payment_entry):
	"""A second genuine Success for a Payment Request that already has a submitted Payment
	Entry: the customer was really charged twice, so this is a refund owed, not a no-op
	(rules/audit-trail.md, rules/payments.md rule 11). The sibling transaction id can be `None`
	— the existing Payment Entry may have come from the Phase 10 poller or a manual action with
	no Paymob Transaction row of its own.
	"""
	attempt.needs_human_attention = 1
	attempt.save(ignore_permissions=True)

	sibling_transaction_id = frappe.db.get_value(
		"Paymob Transaction",
		{
			"payment_request": attempt.payment_request,
			"event_kind": "Success",
			"processed": 1,
			"name": ["!=", transaction.name],
		},
		"paymob_transaction_id",
	)
	if sibling_transaction_id:
		description = _(
			"Paymob confirmed another {0} {1} payment (transaction {2}) for this Payment Request, "
			"which already has a submitted Payment Entry {3} for transaction {4}. A refund is owed "
			"to the customer."
		).format(
			transaction.currency,
			transaction.amount_cents,
			transaction.paymob_transaction_id,
			existing_payment_entry,
			sibling_transaction_id,
		)
	else:
		description = _(
			"Paymob confirmed another {0} {1} payment (transaction {2}) for this Payment Request, "
			"which already has a submitted Payment Entry {3}. A refund is owed to the customer."
		).format(
			transaction.currency,
			transaction.amount_cents,
			transaction.paymob_transaction_id,
			existing_payment_entry,
		)

	audit.record(
		transaction,
		attempt,
		event="Duplicate Payment",
		needs_action=1,
		description=description,
		actor=ACTOR,
		received_amount_cents=transaction.amount_cents,
		received_currency=transaction.currency,
	)
	frappe.logger("paymob").info(
		f"duplicate payment audited payment_request={attempt.payment_request} attempt={attempt.name} "
		f"txn={transaction.paymob_transaction_id} sibling_txn={sibling_transaction_id} "
		f"existing_payment_entry={existing_payment_entry}"
	)
