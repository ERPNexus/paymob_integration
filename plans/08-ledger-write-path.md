# Phase 08 — The Single Ledger Write Path (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** A verified, amount-matched success creates exactly one submitted Payment Entry,
allocated to the Sales Invoice.

**Depends on:** 07. **Blocks:** 09, 10, 11.

## Scope

- `ledger.py` — **the** function. `post_payment(attempt, transaction) -> str`. Nothing else in
  the app inserts a Payment Entry, now or ever.
- Delegates to ERPNext's `PaymentRequest.create_payment_entry(submit=True)`, which builds the
  allocation and links the reference rows back to the Payment Request so the status derives.
- The clearing account comes from `Paymob Credential Set.payment_account`, set on the
  **in-memory** Payment Request document before the call — never saved, so no `db_set` on a
  submitted document (ADR-0008).
- Writes `attempt.payment_entry` and logs one line.

## Must be true

- [ ] `grep -rn "Payment Entry" --include=*.py` shows exactly one insert site.
- [ ] The Payment Entry is submitted (`docstatus == 1`) and its `references` row names the
      Sales Invoice.
- [ ] The Payment Request status becomes `Paid` **because of the allocation**, not because
      anything wrote it.
- [ ] The Sales Invoice `outstanding_amount` becomes 0.
- [ ] The amount posted equals `from_minor_units(transaction.amount_cents, currency)`.
- [ ] A row lock (`for_update=True`) is taken on the attempt before posting.
- [ ] ADR-0008 written.
- [ ] Integration test asserts Payment Entry count, amount, allocation, invoice outstanding, and
      Payment Request status — all four.
