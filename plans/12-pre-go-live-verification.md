# Phase 12 — Pre-Go-Live Verification (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** The behaviours Paymob does not document are measured before real money moves.

**Depends on:** everything.

## Scope — measure, then write down the answer

`docs/must_have_features.md` lists five things the documentation does not settle. Each gets an
experiment and an entry in `docs/reference/endpoints.md` or `decisions.md`.

- [ ] **Webhook retry behaviour.** Point `notification_url` at an endpoint that returns 500, run
      a test payment, and record whether Paymob redelivers, how often, and for how long. Until
      measured, the app assumes zero retries.
- [ ] **Redirect parameter naming.** Log one real redirect and settle `order` vs `order_id` in
      the response-callback HMAC input.
- [ ] **Auth-token lifetime.** Hold a token and inquire until it 401s. Record the measured
      lifetime; adjust `TOKEN_TTL_SECONDS` if it is under 45 minutes.
- [ ] **Intention/Inquiry rate limits.** Run the poller against a batch and record the point at
      which Paymob throttles. Set the batch size below it.
- [ ] **Sandbox-vs-live parity.** Run the full path in test mode, then once with a small **live**
      transaction, and compare callback timing and shape.

## Then

- [ ] Walk `rules/implementation-gate.md` item by item against the whole
      codebase, not just the last diff.
- [ ] Confirm `grep` still finds exactly one Payment Entry insert site.
- [ ] Rotate every credential used during development before going live.
- [ ] `docs/developer-guide/README.md` written: how to integrate, the callback contract, and
      what a reviewer must check.
