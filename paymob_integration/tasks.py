"""Recovers a lost webhook and expires an abandoned checkout. Paymob's webhook retry behaviour
is undocumented and this app assumes it is zero (plans/README.md); this scheduled job is the only
thing that discovers a payment through Transaction Inquiry instead. It produces a Paymob
Transaction row and hands off to `paymob.processor.process_transaction` — it is not a second
Payment Entry write path (rules/payments.md rule 1).
"""

import frappe
from frappe.utils import add_to_date, now_datetime

from paymob_integration.paymob import auth, client, events, processor, settings, states, transactions

INQUIRY_PATH = "/api/ecommerce/orders/transaction_inquiry"
RECONCILE_BATCH_SIZE = 50


def reconcile_pending_attempts():
	"""One attempt's failure never aborts the batch — each attempt is inquired on inside its own
	try/except in the loop below, so a single permanently-failing attempt cannot block the rest.
	"""
	config = settings.get_settings()
	if not settings.is_enabled(config):
		return

	cutoff = add_to_date(now_datetime(), minutes=-(config.stale_pending_minutes or 0))
	rows = frappe.get_all(
		"Paymob Payment Attempt",
		filters={"state": "Pending", "creation": ["<", cutoff]},
		or_filters=[["last_polled_at", "is", "not set"], ["last_polled_at", "<", cutoff]],
		fields=["name", "payment_request"],
		order_by="creation asc",
		limit=RECONCILE_BATCH_SIZE,
	)
	for row in rows:
		try:
			_reconcile(row.name)
		except client.PaymobError:
			frappe.logger("paymob").info(
				f"reconciliation failed payment_request={row.payment_request or 'unknown'} attempt={row.name}"
			)


def _reconcile(attempt_name):
	# Read-then-write on a state field: lock the row before deciding (rules/frappe-discipline.md).
	attempt = frappe.get_doc("Paymob Payment Attempt", attempt_name, for_update=True)
	if attempt.state != "Pending":
		# A webhook landed between selection and now — nothing left for the poller to do.
		return

	try:
		credentials = settings.get_credential_set(attempt.country, attempt.currency, attempt.mode)
	except frappe.ValidationError:
		# Credentials for this attempt's country/currency/mode were disabled or removed after
		# checkout. That's not a Paymob API failure (client.PaymobError), so left uncaught it would
		# abort the whole batch instead of just this attempt. Stamp last_polled_at so a permanently
		# unconfigured attempt doesn't monopolize every bounded batch, and move on.
		attempt.db_set("last_polled_at", frappe.utils.now_datetime())
		frappe.logger("paymob").info(
			f"reconciliation skipped payment_request={attempt.payment_request} attempt={attempt.name} "
			"reason=credentials_unavailable"
		)
		return

	try:
		obj = _inquire(credentials, attempt)
	finally:
		# The only db_set the phase adds. It runs even on a network failure, so one
		# permanently-failing attempt cannot starve newer ones out of every bounded batch — a
		# timestamp is bookkeeping, not payment state.
		attempt.db_set("last_polled_at", frappe.utils.now_datetime())

	if obj is None:
		_expire_if_due(attempt)
	else:
		_hand_off(attempt, obj)


def _inquire(credentials, attempt):
	"""Retries exactly once, on a 401 only. A timeout or 5xx propagates straight out to the
	batch loop; a repeated 401 is not retried again (rules/implementation-gate.md §11).
	"""
	try:
		return _post_inquiry(credentials, attempt, force_refresh=False)
	except client.PaymobAPIError as exc:
		if exc.status_code == 404:
			return None  # Paymob has no transaction for this reference
		if exc.status_code != 401:
			raise  # 5xx / anything else: the batch loop logs and moves on
		frappe.logger("paymob").info(
			f"inquiry auth token refreshed payment_request={attempt.payment_request} attempt={attempt.name}"
		)
	try:
		return _post_inquiry(credentials, attempt, force_refresh=True)
	except client.PaymobAPIError as exc:
		if exc.status_code == 404:
			return None
		raise  # a second 401 is not retried again


def _post_inquiry(credentials, attempt, force_refresh):
	token = auth.get_auth_token(credentials, force_refresh=force_refresh)
	url = f"{settings.base_url(credentials)}{INQUIRY_PATH}"
	return client.request(
		"POST",
		url,
		headers={"Authorization": f"Bearer {token}"},
		json_body={"merchant_order_id": attempt.special_reference},
	)


def _expire_if_due(attempt):
	"""Only an *answered* inquiry that found nothing may expire an attempt
	(rules/implementation-gate.md §11). A timeout, a 5xx or a repeated 401 never reaches here — it
	propagates out of `_inquire` to the batch loop, and the attempt stays Pending for the next
	run. Auth-token expiry and intention expiry share no code path.
	"""
	if not attempt.expires_at or attempt.expires_at > frappe.utils.now_datetime():
		return
	states.check(attempt.state, "Expired")
	attempt.state = "Expired"
	attempt.save(ignore_permissions=True)
	frappe.logger("paymob").info(
		f"attempt expired payment_request={attempt.payment_request} attempt={attempt.name}"
	)


def _hand_off(attempt, obj):
	"""Called directly, not enqueued: the poller is already a background job, and a direct call
	keeps the batch's per-attempt error isolation and makes the integration test synchronous.
	"""
	kind = events.classify_event(obj)
	doc = transactions.store(
		obj, kind, attempt.name, attempt.payment_request, source="Inquiry", hmac_verified=0
	)
	if doc is None:
		# A row for this event already exists (a webhook redelivery, or an earlier inquiry). Reuse
		# it rather than no-op: if its own enqueue/worker crashed before `process_transaction`
		# marked it processed, this reconciliation pass is the only thing left that will ever
		# process it. `process_transaction` is idempotent on `processed`, so if the row was already
		# handled this is a no-op.
		doc = frappe.get_doc(
			"Paymob Transaction",
			transactions.event_key(obj.get("id"), kind, obj.get("refunded_amount_cents")),
		)
	previous_state = attempt.state
	processor.process_transaction(doc.name)
	_log_recovery(attempt, doc, previous_state)


def _log_recovery(attempt, txn, previous_state):
	current_state = frappe.db.get_value("Paymob Payment Attempt", attempt.name, "state")
	if current_state == previous_state:
		return
	frappe.logger("paymob").info(
		f"poller recovery payment_request={attempt.payment_request} attempt={attempt.name} "
		f"from={previous_state} to={current_state}"
	)
