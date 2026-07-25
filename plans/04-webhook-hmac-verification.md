# Phase 04 — Webhook & HMAC Verification (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** A forged callback is refused; an authentic one is acknowledged with 200.

**Depends on:** 01. **Blocks:** 05.

## Scope

- `paymob/hmac_verify.py` — the 20 processed-callback fields in lexicographic key order:
  `amount_cents, created_at, currency, error_occured, has_parent_transaction, id,
  integration_id, is_3d_secure, is_auth, is_capture, is_refunded, is_standalone_payment,
  is_voided, order.id, owner, pending, source_data.pan, source_data.sub_type, source_data.type,
  success`. Booleans render as lowercase `true`/`false`.
- `webhooks.py` — `processed_callback()`, `@frappe.whitelist(allow_guest=True)`.

## Must be true

- [ ] Verification is the **first** statement in the handler — before any document load, amount
      read, or database access.
- [ ] `hmac.compare_digest`, never `==`.
- [ ] Failure returns an error status with **no explanation of why** and writes nothing.
- [ ] The HMAC secret is resolved without trusting the payload: derive the credential set from
      the callback's currency, and try each enabled set if more than one country is configured.
- [ ] No full payload is ever logged — one line with reference, transaction ID, pass/fail.
- [ ] ADR-0006 written: this is the app's only `allow_guest=True` method, and why that does not
      violate `rules/payments.md` rule 17.
- [ ] Unit tests: valid passes; wrong secret rejected; one tampered field rejected; missing
      `hmac` rejected; a payload with fields in a different JSON order still verifies.
