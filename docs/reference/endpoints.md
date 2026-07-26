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
- Route: `paymob_integration.webhooks.processed_callback`, `POST` (JSON body) from Paymob's
  servers, with `?hmac=...` on the URL — **not** in the JSON body.
- `frappe.form_dict` is built from the JSON body only (`make_form_dict`, `request.is_json`);
  `request.args`/`request.form` are never merged in on that path. So `frappe.form_dict.get("hmac")`
  is always `None` for this endpoint — the signature is read from `frappe.request.args.get("hmac")`
  instead. `obj` is read from `frappe.form_dict`, which is safe precisely because the query string
  cannot spoof body fields on the JSON path.
- Auth: verify **HMAC-SHA512** over the fixed field order in
  `paymob/hmac_verify.py::PROCESSED_CALLBACK_FIELDS` (`amount_cents` … `success`, `order.id` not
  `order`) with `hmac.compare_digest`, before any document load or database read of a
  payload-named document.
- The HMAC secret is resolved by **trial verification against every enabled credential set**
  (`settings.enabled_credential_sets()`), not by filtering on a claimed country or currency —
  a payload field must never choose which secret checks it. A forgery matches none; a genuine
  callback matches exactly one. See [ADR-0006](decisions.md#adr-0006--the-processed-callback-is-the-apps-only-allow_guesttrue-method).
- Auth exception: `allow_guest=True` — the app's only one. Paymob's servers hold no Frappe
  session; the HMAC *is* the authentication. See ADR-0006.
- On failure: `frappe.local.response["http_status_code"] = 401`, return nothing — no explanation,
  no document load, no `frappe.db` call.
- On success: classify the event (`paymob.events.classify_event`), resolve the merchant
  order ID against `Paymob Payment Attempt` via `webhooks._resolve_attempt` (one read that
  answers both "does this attempt exist" and "which Payment Request"), insert one
  `Paymob Transaction` row, commit, and return `"ok"`. See
  [ADR-0007](decisions.md#adr-0007--persist-then-acknowledge-the-200-means-committed).
- `merchant_order_id` is **not** covered by the HMAC (only `order.id` is signed — see the field
  list above), so `_resolve_attempt` only trusts the lookup when the attempt's own frozen
  `paymob_order_id` equals the signed `order.id`, mirroring `www/paymob_result.py`'s redirect
  check. A mismatch stores the row with both `attempt` and `payment_request` blank, same as an
  unrecognized reference.
- Status codes:
  - `401` — HMAC did not verify against any enabled credential set. Nothing stored.
  - `200` ("ok") — event durably stored (first delivery of this transaction id + event kind).
  - `200` ("ok") — duplicate delivery (`frappe.DuplicateEntryError` on insert). The row already
    exists; nothing new is written, and Paymob is told to stop retrying.
  - `5xx` — persistence failed for any other reason (`webhooks._store` catches only
    `frappe.DuplicateEntryError`; every other exception propagates and Frappe rolls back). Paymob
    retries, and the Phase 10 poller is the second safety net given Paymob's retry behaviour is
    assumed to be zero.
  - The body is `"ok"` on every 200 — stored or duplicate look identical to the caller, by design.
- No attempt-state change and no Payment Entry yet from this phase — Phase 06 reads the stored
  rows (`processed = 0`) and drives the state machine; Phase 08 posts the ledger entry.
- Ledger authority: **yes** — see [ADR-0001](decisions.md#adr-0001--ledger-writes-are-triggered-only-by-the-server-to-server-processed-callback).

### Response callback (browser redirect target)

**Functional:** The page the customer lands on after paying. It shows a result; it changes nothing.

**Technical:**
- Route: `GET /paymob-result?merchant_order_id=...&hmac=...` — served by
  `paymob_integration/www/paymob_result.py`, template `paymob-result.html`. `no_cache = 1`.
- `merchant_order_id` is looked up directly as the attempt's `special_reference` (its autoname) —
  this lookup key is unsigned and attacker-controlled.
- Loads the attempt first (read-only `frappe.db.get_value`, six columns only) to resolve the
  right per-country/currency/**mode** HMAC secret — the attempt's own stored `mode`, not the
  site's current mode, so an admin flipping Test/Live mid-checkout can't invalidate a legitimate
  redirect — **then** verifies. The one place in the app that reads the database before
  verification, scoped by
  [ADR-0011](decisions.md#adr-0011--the-result-page-resolves-the-credential-set-before-verifying-the-redirect-signature).
- Auth: verify HMAC-SHA512 for display integrity, but **never** write the ledger from here. The
  signed `order` field must also equal the selected attempt's own `paymob_order_id` — otherwise a
  genuinely signed redirect for one attempt could be replayed against another attempt's unsigned
  `merchant_order_id`, borrowing its real state.
- Side effects: render a **generic** result page; the two channels can race, so `Pending` is
  always a correct answer.
- Fails closed: unknown reference, unconfigured credentials, or a bad/missing signature all
  render the same neutral **Pending** page, never a 404 or 500.
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

**Technical:** Reject with `401`, log `reason=no_matching_secret` plus the number of enabled
credential sets tried — nothing payload-derived. At the point verification fails, the payload's
`merchant_order_id` and transaction ID are unverified, attacker-controlled strings; they are
logged only *after* a signature passes. Writes nothing to the ledger.

### Response callback signature failure

**Functional:** A customer whose result-page link was tampered with sees "we're confirming your
payment," never a fake "paid" or "failed."

**Technical:** Unlike the processed callback (which rejects with a `401`), the response callback
still returns `200` and renders the neutral `Pending` message — refusing outright would just be a
worse UX for a page with no ledger authority to protect. Logs `reason=unknown_reference` or falls
through the credential lookup's own narrow exception; never echoes the attacker-supplied
`merchant_order_id` back into the log line.

### Duplicate webhook delivery

**Functional:** The same event arriving twice produces one result, not two.

**Technical:** `Paymob Transaction.name` is `"<transaction_id>:<event_kind>"` — for `Refund`,
`"<transaction_id>:Refund:<refunded_amount_cents>"`
([ADR-0005](decisions.md#adr-0005--the-dedup-key-is-the-rows-own-primary-key-not-a-separate-unique-column));
a repeat insert raises `frappe.DuplicateEntryError`, which `webhooks._store` catches, rolls back,
logs one line, and returns as if stored — `200`, nothing written twice. A later *different* event
for the same transaction (e.g. a refund after a success, or a second partial refund with a larger
`refunded_amount_cents`) has a different name, and remains fully processable.

### Amount mismatch

**Functional:** An authentic callback whose amount differs from what we expected is held for review.

**Technical:** Block auto Payment Entry, raise `needs_human_attention`
([ADR-0003](decisions.md#adr-0003--authentic-amount-mismatch-is-audited-never-auto-posted)).

### Missing callback (abandoned / lost)

**Functional:** If Paymob never calls back, we find out the status ourselves rather than guess.

**Technical:** Scheduled **Transaction Inquiry** (API key → auth token → inquiry); resolve to
`paid`/`failed`/`expired` without deleting audit history.
