# Paymob sandbox smoke test

Use Paymob sandbox credentials only. Record timestamps, document names, transaction IDs, state
transitions, Payment Entry names, amounts, currencies, and pass/fail results only. Never record
credentials, HMAC secrets, card PAN/CVV, customer data, or raw webhook payloads. Refunds are never
retried automatically; do not resend a refund after a timeout. Sandbox evidence does not prove
live-mode readiness by itself.

For each scenario, complete every field: **Setup:** ___ **Action:** ___ **Expected result:** ___
**Observed result:** ___ **Pass/fail:** ___

1. **Successful checkout and valid signed processed callback** — verify one submitted Payment Entry,
   the source invoice reference/allocation, amount, currency, and final states.
2. **Declined payment** — verify no Payment Entry, no invoice settlement, and a retry can create a
   new attempt.
3. **Duplicate callback delivery** — deliver the same signed event twice; verify HTTP success and
   exactly one transaction/payment entry.
4. **Lost webhook and reconciliation inquiry** — omit the callback, run reconciliation, and verify
   the inquiry result follows the normal ledger/allocation path.
5. **Amount mismatch** — verify an audit row, review flag, no Payment Entry, and unchanged invoice.
6. **Currency mismatch** — verify an audit row, review flag, no Payment Entry, and unchanged invoice.
7. **Permission boundary** — verify checkout, refund, and process actions reject unauthorized users.
8. **Partial refund** — verify the signed refund callback creates the correct reversal and remaining
   balance/allocation state.
9. **Full refund** — verify the signed callback creates the full reversal and final refunded state.
10. **Duplicate refund and timeout rule** — verify the lock prevents a duplicate request; after a
    timeout, record the result and do not resend automatically.
11. **Unsupported authorization/capture/void callback** — verify the event is stored/audited for
    review and never posts or changes the ledger.
12. **Callback URL and HTTPS reachability** — verify the configured processed callback is publicly
    reachable over HTTPS and matches the tested site.

Attach this completed checklist to release review only after removing any sensitive evidence.
