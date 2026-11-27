"""The single Payment Entry write path (rules/payments.md rule 1). Every caller — the webhook
processor now, the Phase 10 poller and Phase 11 refund path later — routes through
`post_payment`. Grepping for `create_payment_entry` should return one non-core call site: here.
"""

import frappe
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from frappe.utils import flt, nowdate

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

	credentials = settings.get_credential_set(
		attempt.country, attempt.currency, attempt.mode, settings.attempt_company(attempt)
	)
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

	# Bookkeeping, not money: the custom `payment_request` field (see post_refund) carries no
	# ERPNext validation and matches the Connections tab's default fallback fieldname, so it
	# surfaces this entry there directly, alongside a later refund of the same Payment Request.
	payment_entry.db_set("payment_request", attempt.payment_request)
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


def post_refund(attempt, transaction, delta_cents):
	"""Create the sole money-out entry from a verified refund/void callback.

	`attempt` must already be locked by the caller. A reversal is deliberately on-account: the
	original incoming entry remains allocated to the Payment Request as historical evidence.
	"""
	if not attempt.payment_entry:
		return None

	original = frappe.get_doc("Payment Entry", attempt.payment_entry)
	credentials = settings.get_credential_set(
		attempt.country, attempt.currency, attempt.mode, settings.attempt_company(attempt)
	)
	amount = amounts.from_minor_units(delta_cents, transaction.currency)

	# Mirrors what Payment Entry's own validate() would compute (set_exchange_rate,
	# set_received_amount) — done here explicitly because validate_mandatory() requires
	# received_amount before that auto-fill runs, and only for the same-currency case.
	# Hardcoding both rates to 1 (as before) silently wins over the controller's own
	# recomputation, producing wrong GL amounts whenever a side isn't in company currency.
	company_currency = frappe.get_cached_value("Company", original.company, "default_currency")
	paid_from_currency = frappe.get_cached_value("Account", credentials.payment_account, "account_currency")
	paid_to_currency = frappe.get_cached_value("Account", original.paid_from, "account_currency")
	source_exchange_rate = get_exchange_rate(paid_from_currency, company_currency, nowdate())
	target_exchange_rate = (
		source_exchange_rate
		if paid_to_currency == paid_from_currency
		else get_exchange_rate(paid_to_currency, company_currency, nowdate())
	)
	received_amount = flt(amount * source_exchange_rate / target_exchange_rate)

	payment_entry = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"payment_type": "Pay",
			"company": original.company,
			"party_type": original.party_type,
			"party": original.party,
			"paid_from": credentials.payment_account,
			"paid_to": original.paid_from,
			"paid_amount": amount,
			"received_amount": received_amount,
			"source_exchange_rate": source_exchange_rate,
			"target_exchange_rate": target_exchange_rate,
			"reference_no": transaction.paymob_transaction_id,
			"reference_date": nowdate(),
			# Deliberately no `references` row: ERPNext validates any reference's allocated_amount
			# against its outstanding balance, which is 0 once the original charge is fully paid —
			# a reversal would always fail that check. The original incoming entry stays allocated
			# to the Payment Request as historical evidence. This custom `payment_request` field
			# carries no such validation, and its name matches the default fieldname the
			# Connections tab's count query falls back to, so it surfaces the reversal there too.
			"payment_request": attempt.payment_request,
		}
	)
	payment_entry.insert(ignore_permissions=True)
	if amounts.to_minor_units(payment_entry.paid_amount, transaction.currency) != delta_cents:
		frappe.throw(
			_("Posted refund amount {0} does not match the confirmed refund amount {1}.").format(
				amounts.to_minor_units(payment_entry.paid_amount, transaction.currency), delta_cents
			)
		)
	payment_entry.submit()
	transaction.db_set("payment_entry", payment_entry.name)
	frappe.logger("paymob").info(
		f"refund entry posted payment_request={attempt.payment_request} attempt={attempt.name} "
		f"txn={transaction.paymob_transaction_id} payment_entry={payment_entry.name}"
	)
	return payment_entry.name
