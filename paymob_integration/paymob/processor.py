"""The enqueued consumer of stored Paymob Transaction rows (docs/reference/states.md,
rules/audit-trail.md). Drives Paymob Payment Attempt.state from a verified event, holds an
authentic amount/currency mismatch for a human, and posts the Payment Entry through
`paymob.ledger.post_payment` — the only function that creates one (rules/payments.md rule 1).
"""

import frappe
from frappe import _

from paymob_integration.paymob import amounts, audit, ledger, states, transactions

ACTOR = "paymob_integration.paymob.processor.process_transaction"


def process_transaction(transaction):
	"""Idempotent: a row already marked processed (a requeue after a crash, or a redelivered
	job) is a no-op. Only `states.IllegalTransition` is caught — anything else (a dead database,
	a broken save) propagates so RQ marks the job failed and the row is left for the Phase 10
	poller. Re-raising inside the illegal-transition branch would make RQ retry forever and mint
	a duplicate audit entry on every attempt, so `_refuse` records the audit entry and returns
	instead of raising a second time.

	Runs as Administrator (ADR-0013): `frappe.enqueue` in webhooks.py inherits the calling
	request's user, which is `Guest` for the allow_guest processed callback. ERPNext's
	`create_payment_entry` checks `frappe.has_permission` on the Sales Invoice internally — a
	check `ignore_permissions=True` on our own document saves cannot reach — so a verified,
	HMAC-authenticated event needs a privileged actor to post the money it already proves.
	"""
	original_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		txn = frappe.get_doc("Paymob Transaction", transaction)
		if txn.processed:
			return

		if txn.event_kind not in (*states.EVENT_TARGET, "Refund"):
			return _consume_unmapped(txn)

		if not txn.attempt:
			return _unattributed(txn, states.target_state(txn.event_kind) or "Refunded")

		# Read-then-write on a state field: lock the row before deciding (rules/frappe-discipline.md).
		attempt = frappe.get_doc("Paymob Payment Attempt", txn.attempt, for_update=True)
		if txn.event_kind == "Refund":
			if not txn.has_parent_transaction:
				_mark_processed(txn)
				return
			delta_cents = txn.amount_cents
			total_cents = (attempt.refunded_amount_cents or 0) + delta_cents
			# The same verified charge api._verified_charge caps the outbound request against —
			# not attempt.expected_amount_cents, the pre-charge snapshot — so the two directions
			# can never disagree about how much was actually charged and can be refunded.
			charged = transactions.verified_success_charge(attempt.name)
			charged_cents = charged.amount_cents if charged else 0
			target = states.refund_target(total_cents, charged_cents)
		elif txn.event_kind == "Void":
			delta_cents = attempt.expected_amount_cents - (attempt.refunded_amount_cents or 0)
			total_cents = (attempt.refunded_amount_cents or 0) + delta_cents
			target = "Voided"
		else:
			delta_cents = None
			total_cents = None
			target = states.target_state(txn.event_kind)
		if txn.event_kind == "Refund" and (
			txn.currency != attempt.currency or delta_cents <= 0 or not charged or total_cents > charged_cents
		):
			return _refuse_refund(txn, attempt)
		try:
			moved = states.check(attempt.state, target)
		except states.IllegalTransition:
			return _refuse(txn, attempt, target)

		mismatch = target == "Paid" and not amounts.amounts_match(
			attempt.expected_amount_cents, attempt.currency, txn.amount_cents, txn.currency
		)

		previous_state = attempt.state
		if moved:
			attempt.state = target
		if mismatch:
			attempt.needs_human_attention = 1
		attempt.save(ignore_permissions=True)

		if mismatch:
			audit.record(
				txn,
				attempt,
				event="Amount Mismatch",
				needs_action=1,
				description=_("Paymob confirmed {0} {1} but {2} {3} was expected.").format(
					txn.currency, txn.amount_cents, attempt.currency, attempt.expected_amount_cents
				),
				actor=ACTOR,
				expected_amount_cents=attempt.expected_amount_cents,
				expected_currency=attempt.currency,
				received_amount_cents=txn.amount_cents,
				received_currency=txn.currency,
			)
			frappe.logger("paymob").info(
				f"amount mismatch payment_request={attempt.payment_request} attempt={attempt.name} "
				f"txn={txn.paymob_transaction_id} expected={attempt.expected_amount_cents}{attempt.currency} "
				f"received={txn.amount_cents}{txn.currency}"
			)

		if target == "Paid" and not mismatch:
			ledger.post_payment(attempt, txn)
		elif txn.event_kind in ("Refund", "Void"):
			ledger.post_refund(attempt, txn, delta_cents)
			attempt.refunded_amount_cents = total_cents
			attempt.refund_requested_at = None
			attempt.save(ignore_permissions=True)

		_mark_processed(txn)
		frappe.logger("paymob").info(
			f"state changed payment_request={attempt.payment_request} attempt={attempt.name} "
			f"txn={txn.paymob_transaction_id} kind={txn.event_kind} from={previous_state} to={attempt.state}"
		)
	finally:
		frappe.set_user(original_user)


def _consume_unmapped(txn):
	"""`Pending` is consumed — there is nothing left to do with a wallet/kiosk in-flight
	notification. `Auth`/`Capture` map to no state yet and are left
	unprocessed so that phase's poller/consumer can pick the row up.
	"""
	if txn.event_kind != "Pending":
		frappe.logger("paymob").info(
			f"unmapped event kind left unprocessed payment_request={txn.payment_request or 'unknown'} "
			f"txn={txn.paymob_transaction_id} kind={txn.event_kind}"
		)
		return
	_mark_processed(txn)
	frappe.logger("paymob").info(
		f"pending event consumed payment_request={txn.payment_request or 'unknown'} "
		f"txn={txn.paymob_transaction_id}"
	)


def _unattributed(txn, target):
	"""A Success/Refund with no resolved attempt is real money we cannot post — audited for a
	human. A Decline with no attempt is a stray scan callback, not accountant homework.
	"""
	if target == "Failed":
		_mark_processed(txn)
		frappe.logger("paymob").info(
			f"unattributed decline logged txn={txn.paymob_transaction_id} kind={txn.event_kind}"
		)
		return
	audit.record(
		txn,
		None,
		event="Unattributed Payment",
		needs_action=1,
		description=_("Paymob reported a {0} of {1} {2} that could not be matched to any attempt.").format(
			_(txn.event_kind), txn.currency, txn.amount_cents
		),
		actor=ACTOR,
		received_amount_cents=txn.amount_cents,
		received_currency=txn.currency,
	)
	_mark_processed(txn)
	frappe.logger("paymob").info(
		f"unattributed payment audited txn={txn.paymob_transaction_id} kind={txn.event_kind}"
	)


def _refuse(txn, attempt, target):
	"""`states.check` already raised and `frappe.throw`'s message is not re-raised here — doing
	so would be a second exception on top of the one `states.check` already threw. This is the
	durable record instead: flag the attempt, keep its current state, audit, and mark the
	transaction processed so the job does not requeue forever on a transition that will never
	become legal.
	"""
	attempt.needs_human_attention = 1
	attempt.save(ignore_permissions=True)
	audit.record(
		txn,
		attempt,
		event="Illegal Transition",
		needs_action=1,
		description=_("Paymob reported {0}, which would move this payment from {1} to {2}.").format(
			_(txn.event_kind), _(attempt.state), _(target)
		),
		actor=ACTOR,
	)
	_mark_processed(txn)
	frappe.logger("paymob").info(
		f"state change refused payment_request={attempt.payment_request} from={attempt.state} to={target}"
	)


def _refuse_refund(txn, attempt):
	"""Hold an authentic but impossible refund amount for human review; post nothing."""
	attempt.needs_human_attention = 1
	attempt.save(ignore_permissions=True)
	audit.record(
		txn,
		attempt,
		event="Amount Mismatch",
		needs_action=1,
		description=_("Paymob reported a refund amount or currency that cannot be applied to this attempt."),
		actor=ACTOR,
		expected_amount_cents=attempt.expected_amount_cents,
		expected_currency=attempt.currency,
		received_amount_cents=txn.amount_cents,
		received_currency=txn.currency,
	)
	_mark_processed(txn)
	frappe.logger("paymob").info(
		f"refund refused payment_request={attempt.payment_request} attempt={attempt.name} "
		f"txn={txn.paymob_transaction_id}"
	)


def _mark_processed(txn):
	"""`processed` is bookkeeping, not money — the documented db_set exception alongside
	last_polled_at (rules/frappe-discipline.md).
	"""
	txn.db_set("processed", 1)
