# Phase 09 — Duplicate Payment Guard (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** Two genuine payments for one Payment Request produce one Payment Entry and one refund
flag, not an overpaid invoice.

**Depends on:** 08.

## Scope

- `ledger.py` — before posting, check whether a submitted Payment Entry already references this
  Payment Request (ERPNext's own `Payment Entry Reference` query is the model).
- If one exists: audit entry `Duplicate Payment`, `needs_action=1`, description naming both
  transaction IDs, and no second posting.

## Must be true

- [ ] This check is **separate** from the Phase 05 dedup. Different transaction IDs pass that
      one; this is the second guard.
- [ ] The customer really was charged twice, so the audit entry says a refund is owed — it does
      not say "duplicate, ignored".
- [ ] The check runs inside the same lock as the posting.
- [ ] Integration test: two verified successes with different transaction IDs → one Payment
      Entry, two Paymob Transaction rows, one audit entry flagged for action.
