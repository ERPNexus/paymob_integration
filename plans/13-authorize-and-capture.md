# Phase 13 — Authorize & Capture (outline)

**Goal:** A verified auth-only callback holds funds without posting; a permitted staff member can
capture it once, and the verified capture callback posts through the existing ledger path.

**Depends on:** 11.

## Scope

- `Authorized` lifecycle state plus `Auth`/`Capture` event targets.
- A locked, permission-gated full-capture request and independent capture latch.
- Authorization-aware void, capture UI, operational count, tests, docs, and translations.

## Must be true

- [ ] Auth creates no Payment Entry; only the verified, matched Capture callback can post one.
- [ ] Capture/refund/void cannot overlap and outbound capture is never retried.
- [ ] An authorization void posts no reversal and never grows `refunded_amount_cents`.
- [ ] Refunds use a verified actual charge, never an uncaptured authorization.
- [ ] `capture_mode` is documented merchant intent only; callback facts determine state.
