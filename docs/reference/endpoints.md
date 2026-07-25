# Endpoints, Settings & Errors

Callback/API endpoints (auth + side effects), configuration settings, and named failure paths.
Governed by [../../rules/documentation.md](../../rules/documentation.md).

## Endpoints

### Processed callback (server-to-server webhook)

**Functional:** How Paymob's servers tell us the real outcome of a payment. This is the only
message that can cause money to be recorded.

**Technical:**
- Method: `POST` (JSON) from Paymob's servers, with `?hmac=...` on the URL.
- Auth: verify **HMAC-SHA512** with the HMAC secret before anything else.
- Side effects: idempotency check → legal state transition → Payment Entry (if success + amount matches).
- Ledger authority: **yes** — see [ADR-0001](decisions.md#adr-0001--ledger-writes-are-triggered-only-by-the-server-to-server-processed-callback).

### Response callback (browser redirect target)

**Functional:** The page the customer lands on after paying. It shows a result; it changes nothing.

**Technical:**
- Method: `GET` from the customer's **browser**, with `&hmac=...` query params.
- Auth: verify HMAC for display integrity, but **never** write the ledger from here.
- Side effects: render a **generic** result page ("we're confirming…"); the two channels can race.
- Ledger authority: **no**.

## Settings

### Integration IDs (child table)

**Functional:** Which Paymob payment methods this site offers, and their mode/currency.

**Technical:**
- Stored as a **child table** (method, currency, mode, integration ID) — not a single field.
- Each integration ID is a mode-bound (`test`/`live`) payment-method contract. Test and live IDs
  must match the key mode in use, or checkout fails.

### Credential storage

**Functional:** Where the Paymob keys are kept.

**Technical:**
- Stored in secure Frappe/site configuration — **never** committed to the repo.
- Server-only credentials (secret key, API key, HMAC secret) are never sent to the browser
  ([ADR-0002](decisions.md#adr-0002--server-only-credentials-never-reach-the-browser)).

## Named error paths

### HMAC verification failure

**Functional:** A callback that can't be proven to come from Paymob is refused.

**Technical:** Reject (e.g. `401`), log the event, write nothing to the ledger.

### Duplicate webhook delivery

**Functional:** The same event arriving twice produces one result, not two.

**Technical:** Idempotency check on `transaction_id` + event type; acknowledge and exit on duplicate.
A later *different* event for the same transaction (e.g. a refund) remains processable.

### Amount mismatch

**Functional:** An authentic callback whose amount differs from what we expected is held for review.

**Technical:** Block auto Payment Entry, raise `needs_human_attention`
([ADR-0003](decisions.md#adr-0003--authentic-amount-mismatch-is-audited-never-auto-posted)).

### Missing callback (abandoned / lost)

**Functional:** If Paymob never calls back, we find out the status ourselves rather than guess.

**Technical:** Scheduled **Transaction Inquiry** (API key → auth token → inquiry); resolve to
`paid`/`failed`/`expired` without deleting audit history.
