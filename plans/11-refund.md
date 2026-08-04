# Phase 11 — Refund (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** Staff refund from ERPNext, under a lock, and the reversing entry is posted from the
verified callback — not from the API response.

**Depends on:** 08.

## Scope

- `api.py` — `request_refund(attempt, amount)`, whitelisted,
  role-gated to a new **Paymob Refund Manager** role.
- `POST /api/acceptance/void_refund/refund` `{transaction_id, amount_cents}`.
- The resulting callback is the *parent* transaction re-sent with `is_refunded: true` and a
  growing `refunded_amount_cents`; the refund itself is a child transaction with
  `parent_transaction` set.

## Must be true

- [ ] A **server-side lock** on the attempt is taken *before* the API call. A disabled button is
      not a defense, and neither is trusting Paymob to reject the second request.
- [ ] Refunds are **never** retried automatically. Paymob takes no idempotency
      key; a retry is new money movement.
- [ ] No Payment Entry is created from the refund call's HTTP 200. The reversing entry comes
      from the verified callback, through the single write path.
- [ ] Partial refunds arrive several times with cumulative `refunded_amount_cents` — each posts
      the *delta*, once, and the arithmetic is in integer cents.
- [ ] The requested refund amount is validated against verified Paymob data, never against a
      browser-supplied number.
- [ ] Every refund request creates an audit entry naming the actor and the parameters.
- [ ] A user without the role is refused. Test it.
- [ ] Integration test: double-submitted refund → one outbound call. This is the scenario the
      lock exists for.
