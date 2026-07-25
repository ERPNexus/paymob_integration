# Phase 03 — Customer Result Page (outline)

> Outline only. Expand into a full task-by-task plan before implementing.

**Goal:** The customer's browser lands on `/paymob-result` after checkout and sees a status
message driven by our own stored state, never by the URL parameters.

**Depends on:** 02. **Blocks:** nothing.

## Scope

- `www/paymob-result.py` + `.html` — guest-accessible website page.
- `paymob/hmac_verify.py` — the **response callback** field list and verifier (the processed
  callback's different field list arrives in Phase 04).
- Page reads the `Paymob Payment Attempt` by `merchant_order_id`, renders a generic message per
  `state`: Pending → "we're confirming your payment", Paid → "payment received", Failed →
  "payment did not go through, you can try again", Expired → "this payment link has expired".

## Must be true

- [ ] Nothing on this page writes to the ledger or changes any state (ADR-0001).
- [ ] The response HMAC is verified; a failed verification still renders the *pending* page and
      logs a rejected-display line — it never renders "paid".
- [ ] The page shows no amount, no transaction ID, no invoice number, and no Paymob identifiers.
- [ ] The webhook and the redirect can arrive in either order; "Pending" is a correct answer.
- [ ] Empirically confirm whether the redirect sends `order` or `order_id` (docs disagree) and
      record the answer in `docs/reference/endpoints.md`.
- [ ] Unit tests: valid signature passes, tampered field rejected, missing `hmac` rejected.
- [ ] Integration test: a paid attempt renders the paid message; an unknown reference renders a
      neutral page and does not 500.
- [ ] All four messages translated in `ar.csv`.
- [ ] `docs/reference/endpoints.md` response-callback entry updated with the real route.
