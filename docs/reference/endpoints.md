# Endpoints, Settings & Errors

Callback/API endpoints (auth + side effects), configuration settings, and named failure paths.
Governed by [../../rules/documentation.md](../../rules/documentation.md).

## Endpoints

### Start checkout

**Functional:** A Desk user starts a hosted Paymob checkout from a submitted Payment Request.

**Technical:** `paymob_integration.api.start_checkout(payment_request)` requires `write`
permission on that incoming Payment Request. It reads the amount and currency from the request and
the merchant region from `Company.country`, creates a pending attempt, commits its unique reference,
then calls Paymob's Intention API. Customer billing country is separate: the selected customer
address falls back to the party's primary address, and is sent as the uppercase ISO `Country.code`
or Paymob's `NA` placeholder. It returns only the attempt name and hosted URL containing the public
key and per-session client secret. Ledger
authority: **no**. The Intention call is never retried.

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

### Paymob Settings (Single)

**Functional:** One place where a merchant enters their Paymob account details, one set per
country they sell in, and switches the whole site between test and live.

**Technical:**
- `enabled` gates credential resolution. `mode` (`Test`/`Live`) selects credential rows; there
  is **no fallback** from Live to Test.
- `credential_sets` stores country, currency, mode, base URL, browser-safe `public_key`, encrypted
  `secret_key`/`api_key`/`hmac_secret`, and the clearing `payment_account`.
- `integration_ids` stores the checkout methods keyed by country, currency, and mode.
- `intention_expiration_seconds` defaults to 3600 and `stale_pending_minutes` to 20.
- Only System Managers can read or edit the settings.

### Test Connection

**Functional:** A button proves saved Paymob credentials work before a customer relies on them.

**Technical:**
- Whitelisted method `test_connection(country, currency)` requires `System Manager`.
- It requests `POST {base_url}/api/auth/tokens`, caches the discarded auth token, and returns only
  `{ok, message}`; no token or key is returned or logged.
- Ledger authority: none.
- Expected Paymob failures are surfaced as short translated Desk messages without an endpoint,
  response body, credential, or traceback.

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
