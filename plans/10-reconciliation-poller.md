# Phase 10 — Reconciliation & Expiry (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** A lost webhook is recovered without a human noticing, and an abandoned checkout stops
blocking the invoice.

**Depends on:** 08.

## Scope

- `tasks.py` — `reconcile_pending_attempts()`, registered in `hooks.py` `scheduler_events`
  (cron, default every 15 minutes).
- Selects attempts in state `Pending` older than `stale_pending_minutes`.
- `POST /api/ecommerce/orders/transaction_inquiry` with `{merchant_order_id}`, authenticated
  with the **Bearer auth token** from Phase 01 (not the secret key).
- A found transaction is written as a `Paymob Transaction` with `source = "Inquiry"` and goes
  through the **same** `process_transaction` path as a webhook.
- An attempt past `expires_at` with no transaction becomes `Expired`.

## Must be true

- [ ] The poller creates no second write path — it produces a Transaction row and hands off.
- [ ] A 401 refreshes the auth token and retries **once**, keeping the payment `Pending`.
- [ ] A timeout or 5xx changes nothing, logs, and leaves the attempt for the next run.
- [ ] Auth-token expiry and intention expiry do not share a code path. Only the second is
      terminal.
- [ ] `last_polled_at` is the one field written with `db_set`.
- [ ] Batch size is bounded — Paymob's rate limits are undocumented.
- [ ] A poller-driven state change creates an audit entry (`rules/audit-trail.md`).
- [ ] Integration test: webhook never delivered → poller finds the transaction → one Payment
      Entry through the shared function. Assert the count is one, not that it "worked".
