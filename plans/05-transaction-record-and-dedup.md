# Phase 05 — Transaction Record & Dedup (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** An authentic callback is stored exactly once. The same delivery twice stores nothing
extra and still returns 200.

**Depends on:** 04. **Blocks:** 06.

## Scope

- `Paymob Transaction` doctype — append-only event record. Key fields: `attempt`,
  `payment_request`, `paymob_transaction_id`, `event_kind`, `event_key` (**unique**),
  `amount_cents`, `currency`, `success`, `pending`, `is_refunded`,
  `refunded_amount_cents`, `source` (`Webhook`/`Inquiry`), `hmac_verified`, `received_at`,
  `raw_payload`, `processed`.
- `paymob/events.py` — `classify_event(obj) -> str` mapping the flags to one of
  `Success`, `Decline`, `Refund`, `Pending`, or `Unsupported`. Auth, Capture, and Void flags are
  stored only as signed facts behind `Unsupported`. There is no event-type field in the payload.
- `webhooks.py` — verify → classify → insert → commit → `frappe.enqueue` → return 200.

## Must be true

- [ ] `event_key = f"{paymob_transaction_id}:{event_kind}"`, computed in `validate`, `unique=1`.
      Verify the unique index reached MariaDB with `SHOW INDEX`.
- [ ] A duplicate raises `frappe.DuplicateEntryError`, which is caught **specifically** and
      turned into HTTP 200 with no new row. Not a bare `except`.
- [ ] A *different* event for the same transaction ID (a later refund) still inserts.
- [ ] The 200 is returned only after the row is committed (ADR-0007).
- [ ] A failure to persist returns a non-2xx.
- [ ] `raw_payload` is stored (Paymob already masks the PAN) but never written to a log.
- [ ] Integration tests: same payload twice → one row, two 200s; refund after success → two rows.
- [ ] ADR-0005 (`event_key`) and ADR-0007 (persist-then-acknowledge) written.
