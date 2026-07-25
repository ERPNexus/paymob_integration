# Phase 06 — State Machine & Audit Trail (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** A verified success moves the attempt to `Paid`. An illegal transition is refused and
leaves a durable record.

**Depends on:** 05. **Blocks:** 07.

## Scope

- `paymob/states.py` — the legal transition table from `docs/reference/states.md`:
  `Pending → Paid | Failed | Expired`, `Paid → Refunded`. Everything else raises.
- `Paymob Audit Entry` doctype — submittable, immutable. Fields: `payment_request`, `attempt`,
  `paymob_transaction_id`, `event`, `description`, `expected_amount_cents`,
  `received_amount_cents`, `actor`, `occurred_at` (UTC), `needs_action`, `supersedes`.
- `Paymob Open Audit Entries` Query Report — the "needs action" view, because a list filter
  cannot express "has no superseding record".
- `processor.py` — `process_transaction(name)`, the enqueued job. Loads the transaction, derives
  the target state, applies it.

## Must be true

- [ ] `Failed → Paid` and `Paid → Failed` both raise and create an audit entry.
- [ ] The attempt's state is changed through the document API, never `db_set`.
- [ ] A decline sets state `Failed` and touches nothing else: no Payment Entry, no GL row, the
      Sales Invoice unchanged, and a new attempt is still possible. Assert by counting rows.
- [ ] No code path edits or deletes an audit entry. A resolution is a new entry with
      `supersedes` set.
- [ ] An accountant can open the report and see what needs action without writing SQL.
- [ ] ADR-0009 written (immutable audit + supersede).
- [ ] Unit tests for every legal and illegal transition, driven by a table.
