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
- After the row's commit, `frappe.enqueue`s `paymob.processor.process_transaction` on the
  `short` queue, with `job_id=f"paymob-process-{doc.name}"` and `deduplicate=True` so a
  redelivery that somehow slips past the primary-key constraint still cannot double-enqueue. A
  duplicate delivery (`doc` is `None`) enqueues nothing — there is no new row to process.
- `paymob.processor.process_transaction` drives the state machine, holds a mismatch for review,
  and posts the Payment Entry through `paymob.ledger.post_payment` when the event targets `Paid`
  cleanly.
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

### Transaction Inquiry

**Functional:** How ERPNext finds out what really happened to a payment when Paymob's own
confirmation message never arrives.

**Technical:**
- Route: `POST {base_url}/api/ecommerce/orders/transaction_inquiry`, called from
  `paymob.tasks._post_inquiry` — never called directly by a user, only from the scheduled
  `paymob.tasks.reconcile_pending_attempts` cron job.
- Auth: **Bearer auth token** (`paymob.auth.get_auth_token`, API key → 45-minute cached token) —
  **not** the secret key `paymob.intention` uses to create an intention. Body:
  `{"merchant_order_id": attempt.special_reference}`.
- Retryable: **yes** — this is a read (`rules/implementation-gate.md` §10). On a `401`, the poller
  refreshes the token once (`force_refresh=True`) and retries the inquiry exactly once; a second
  `401` is not retried again. A timeout or `5xx` changes nothing and leaves the attempt for the
  next scheduled run — see
  [ADR-0014](decisions.md#adr-0014--only-an-answered-inquiry-may-expire-an-attempt).
- A `404` means "no transaction exists for this reference" — the one answer that may lead to
  `Expired` (only if `attempt.expires_at` has also passed). A found transaction is written through
  `paymob.transactions.store(..., source="Inquiry", hmac_verified=0)` and handed to
  `paymob.processor.process_transaction` — the very same consumer the webhook enqueues, called
  directly rather than enqueued, since the poller is already a background job.
- Ledger authority: **yes**, indirectly — the same `process_transaction` → `paymob.ledger.
  post_payment` path the webhook uses, not a second write path (rules/payments.md rule 1).

### Request refund

**Functional:** A staff member holding the `Paymob Refund Manager` role's `refund` permission
refunds a paid Paymob payment, in full or in part, from the Payment Request.

**Technical:**
- `paymob_integration.api.request_refund(attempt, amount_cents)`, whitelisted `POST`.
- `attempt = frappe.get_doc("Paymob Payment Attempt", attempt, for_update=True)` — the row lock,
  taken **before** the permission check or anything slow, so a concurrent second request blocks
  here rather than racing past. `attempt.check_permission("refund")` — the custom Permission Type
  gate, derived from the DocType's own `permissions` list, not a hardcoded role name. See
  [ADR-0019](decisions.md#adr-0019--refund-capability-is-a-doctype-permission).
- If `attempt.refund_requested_at` is already set, throws [Refund already in progress](#refund-already-in-progress)
  — this is what actually stops a double submit; the lock alone does not, because a second request
  simply waits for the first to commit and then proceeds. See
  [ADR-0018](decisions.md#adr-0018--a-lock-needs-an-in-progress-marker).
- If `attempt.capture_requested_at` is set, throws
  [Capture already in progress](#capture-already-in-progress): a capture in flight must resolve
  before a refund can be requested against the same attempt.
- `amount_cents` is browser-supplied and validated against **verified Paymob data only**: it must
  be a positive integer, and it is capped by `paymob.transactions.verified_charge(attempt)` — the
  attempt's own HMAC-verified `Capture` or `Success` row, whichever is verified (a captured
  authorization has no `Success` row of its own) — minus `attempt.refunded_amount_cents` — never
  against a client-supplied total. The `transaction_id` sent to Paymob comes from that same
  verified row, never from the browser.
- Sets the in-progress marker (`refund_requested_at`), writes a `Refund Requested`
  `Paymob Audit Entry` naming `frappe.session.user`, then calls the Paymob refund endpoint below.
  **No Payment Entry is created here** — the response body is not read for money. If the outbound
  call raises, the marker stays set; only the verified callback clears it (Task 5 below).
- Ledger authority: **no**. The reversing entry is written only by `paymob.ledger.post_refund`,
  only from a verified callback.

### Request void

**Functional:** Releases an uncaptured authorization hold in full — no amount parameter, since a
void releases the whole hold. Money that already moved is refunded instead, never voided, so the
Desk offers **Void** only on an `Authorized` attempt and **Refund** only on a `Paid` or
`Partially Refunded` one; the two are alternatives and are never shown together.

**Technical:** `paymob_integration.api.request_void(attempt)`, whitelisted `POST`. Same lock,
permission gate, and in-progress marker as Request refund, plus the same capture-in-progress
refusal. The state guard requires `Authorized`; anything else throws. The transaction reversed is
always the verified authorization (`paymob.transactions.verified_authorization` — an `Auth` row, or
a `Success` row retargeted to `Authorized` under
[ADR-0028](decisions.md#adr-0028--an-unprovable-capture-is-recorded-as-a-hold)), never the
verified charge. Writes a `Void Requested` audit entry. Ledger authority: **no**, same as Request
refund.

This narrows only what *this app sends*. An inbound verified `Void` callback on a `Paid` attempt
still processes and still posts its reversal — a merchant can void from Paymob's own dashboard, and
`states.LEGAL["Paid"]` keeps `Voided` for exactly that
([ADR-0026](decisions.md#adr-0026--a-hold-paymob-captures-anyway-is-posted-and-audited)).

### Paymob refund, void, and capture calls

**Functional:** The three outbound HTTP calls Request refund/void/capture make to Paymob.

**Technical:**
- `paymob.void_refund.refund(credentials, transaction_id, amount_cents)` →
  `POST {base_url}/api/acceptance/void_refund/refund`; `paymob.void_refund.void(credentials,
  transaction_id)` → `POST {base_url}/api/acceptance/void_refund/void`;
  `paymob.void_refund.capture(credentials, transaction_id, amount_cents)` →
  `POST {base_url}/api/acceptance/capture`. All three go through `paymob.auth.get_auth_token` and
  the app's one network module, `paymob.client.request`.
- Auth token in the JSON **body** (`auth_token`), the older Accept convention — not an
  `Authorization` header like Transaction Inquiry. Marked `ponytail` in `void_refund.py`: switch
  this if a live sandbox call proves otherwise.
- Retryable: **no** — the opposite of Transaction Inquiry. Capture, refund, and void may never be
  retried automatically (`rules/payments.md` rule 13); a `PaymobNetworkError` or `PaymobAPIError`
  propagates straight to the caller, which leaves the in-progress marker set rather than
  re-issuing the call.
- Ledger authority: **no** — the HTTP response is not evidence money moved; only the signed
  callback that follows is (see [Processed callback](#processed-callback-server-to-server-webhook)
  above — the same route handles refund, void, and capture callbacks).

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
- `intention_expiration_seconds` defaults to 3600 and `stale_pending_minutes` to 20. The
  reconciliation poller (`paymob.tasks.reconcile_pending_attempts`) processes up to 50 attempts
  per scheduled run every 15 minutes via `scheduler_events`
  (`"cron": {"*/15 * * * *": [...]}`) in `hooks.py`. The poller returns immediately if `enabled`
  is `0`.
- Only System Managers can read or edit the settings.
- `send_payment_link_email` defaults to `1`. When it is enabled, an eligible submitted inward
  Payment Request receives an app-owned signed payment URL through ERPNext's existing email flow;
  when it is disabled, that email is muted rather than sent without a Paymob link. Either way the
  decision is made on `validate`, before ERPNext's `before_submit` sends the mail
  ([ADR-0024](decisions.md#adr-0024--the-payment-link-email-is-decided-at-validate)); `mute_email`
  remains the per-request opt-out.
- `send_status_emails` defaults to `1` and switches every seeded Paymob Notification on or off in
  one place.

### Payer payment link

**Functional:** The link in a Payment Request email opens a current Paymob checkout for the payer.

**Technical:** `GET /paymob-pay?ref=...&_signature=...` is served by
`paymob_integration/www/paymob_pay.py` with `no_cache = 1`. `verify_request()` runs before its only
database access. The route reuses a ready `Pending` attempt only while `expires_at` is in the future;
otherwise it calls the shared checkout path and redirects to Paymob. Validation or gateway failures show
a translated generic page, log the Payment Request reference, and leave payment state unchanged.

### Test Connection

**Functional:** A button proves saved Paymob credentials work before a customer relies on them.

**Technical:**
- Whitelisted method `test_connection(country, currency)` requires `System Manager`.
- It requests `POST {base_url}/api/auth/tokens`, caches the discarded auth token, and returns only
  `{ok, message}`; no token or key is returned or logged.
- Ledger authority: none.
- Expected Paymob failures are surfaced as short translated Desk messages without an endpoint,
  response body, credential, or traceback.

### Process (manual rescue)

**Functional:** A button on a Paymob Transaction stuck at "Processed: No" runs it through the
state machine now, instead of waiting for the background job or Phase 10's poller.

**Technical:**
- Whitelisted method `paymob_transaction.process(name)` calls
  `frappe.get_doc("Paymob Transaction", name).check_permission("read")` — the same roles that can
  read the doctype, taken from `paymob_transaction.json` rather than a hardcoded role list — then
  `processor.process_transaction(name)` (ADR-0013).
- It never calls Paymob's API; it re-runs our own idempotent consumer of an already-stored,
  already-HMAC-verified row. A no-op on an already-processed row, same as the automatic path.
- Ledger authority: none directly — it can trigger `paymob.ledger.post_payment` the same way the
  automatic path does, under the same duplicate-payment guard.

## Named error paths

### No enabled Integration ID configured

**Functional:** A checkout is refused, before Paymob is ever contacted, when nothing is configured
for the merchant's country, currency, and mode.

**Technical:** `paymob.settings.resolve_integrations` throws when no *enabled* `Paymob Integration
ID` row matches `(country, currency, config.mode)`, naming all three in the message. There is no
fallback to another mode or currency. See
[ADR-0027](decisions.md#adr-0027--capture-mode-is-a-paymob-settings-property).

### Mixed Capture Modes

**Functional:** A group of Integration IDs that disagree on whether to charge immediately or hold
is refused — both when a System Manager tries to save that configuration, and again at checkout
for rows that reached the database some other way (fixture, console). Left unrefused, Paymob's
hosted checkout would render one button per integration ID and let the **payer** decide whether
their card is charged or held.

**Technical:** `paymob.settings.capture_mode_for` throws when the enabled rows sharing one
`(country, currency, mode)` carry more than one distinct `capture_mode`, naming the trio and both
conflicting modes. Called from `Paymob Settings.validate` (blocks the save) and
`paymob.settings.resolve_integrations` (blocks the checkout) — the same function, so the rule
cannot drift between the two gates. See
[ADR-0027](decisions.md#adr-0027--capture-mode-is-a-paymob-settings-property).

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

**Technical:** `paymob.processor.process_transaction` compares `txn.amount_cents`/`txn.currency`
against `attempt.expected_amount_cents`/`attempt.currency` with `amounts.amounts_match` (integer
cents, currency case/whitespace-insensitive) whenever the event targets `Paid`. A mismatch — under,
over, or right-amount-wrong-currency — sets `attempt.needs_human_attention = 1` and writes one
`Amount Mismatch` `Paymob Audit Entry` with both amounts and both currencies; **the lifecycle state
still moves to `Paid`**, per [ADR-0003](decisions.md#adr-0003--authentic-amount-mismatch-is-audited-never-auto-posted) —
the flag blocks `paymob.ledger.post_payment` from running at all (`processor.process_transaction`
gates the call on `target == "Paid" and not mismatch`), it does not regress the state. No Payment
Entry is created on a mismatched callback.

### Illegal transition

**Functional:** A callback that would move a payment backward (e.g. reporting a decline for a
payment already paid) is refused and left for a human, without crashing or retrying forever.

**Technical:** `paymob.processor.process_transaction` loads the attempt with `for_update=True` and
calls `paymob.states.check(current, target)`; only `states.IllegalTransition` is caught. The
attempt's state is left unchanged, `needs_human_attention` is set, one `Illegal Transition`
`Paymob Audit Entry` is written, and the transaction row is marked `processed = 1` so the job does
not requeue on a transition that will never become legal. The exception is not re-raised — doing
so would be a second exception on top of the one `states.check` already threw.

### Unattributed payment

**Functional:** A genuine `Success` or `Refund` that cannot be matched to any attempt is real
money that cannot be posted anywhere — held for a human rather than silently dropped. An
unmatched `Auth` is different: it is an authorization hold, not money that moved, but a human
still needs to locate and void or capture it directly through Paymob's own tools. A stray
`Decline` with no matching attempt (a scan, not a real checkout) is just logged.

**Technical:** `paymob.processor._unattributed` writes one `Unattributed Payment` audit entry
(`needs_action = 1`, `attempt` blank) for `Success`/`Refund`/`Auth` rows whose `attempt` link is
empty — the case `webhooks._resolve_attempt` produces when `merchant_order_id` doesn't resolve, or
resolves to an attempt whose frozen `paymob_order_id` doesn't match the signed `order.id`. The
`Auth` case gets a distinct description naming it a hold, not a payment. A `Decline` with no
attempt writes no audit entry. All mark the row `processed = 1`.

### Duplicate payment for one Payment Request

**Functional:** A second genuine payment for a Payment Request that already has one is real money
that was charged twice — held for a human to refund, not silently dropped or posted again.

**Technical:** Distinct from the [duplicate webhook delivery](#duplicate-webhook-delivery) case
above: that one is the *same* transaction id redelivered, caught by the primary-key constraint
before `process_transaction` ever runs. This is a *different*, genuine `Success` transaction id
for an attempt whose Payment Request already has a submitted Payment Entry —
`states.check` treats `current == target` as a legal no-op, so it reaches
`paymob.ledger.post_payment`, which looks up `Payment Entry Reference` for an existing submitted
row against the same `payment_request` before doing anything else, inside the same
`for_update=True` lock the caller already holds. Finding one skips posting entirely: the attempt is
flagged `needs_human_attention = 1`, and one `Duplicate Payment` `Paymob Audit Entry` is written
naming the existing Payment Entry and, when it exists, the sibling transaction id — the current
transaction row is still marked `processed = 1` so the job does not retry. See
[ADR-0012](decisions.md#adr-0012--the-audit-writer-moved-to-its-own-module).

### Refund already in progress

**Functional:** A second click on Refund or Void while the first request is still in flight is
refused, rather than firing a second outbound call to Paymob.

**Technical:** `api.request_refund`/`request_void` check `attempt.refund_requested_at` immediately
after taking the row lock and the permission check. The row lock alone does not prevent this —
without the marker, a second concurrent request would simply block until the first commits, then
proceed and call Paymob a second time. `refund_requested_at` is set inside the same lock as the
check, so it becomes visible to a blocked second request the instant the first commits, and is
cleared only when the verified refund/void callback is processed — never by the outbound call's
HTTP response, success or failure. A stuck marker (the outbound call failed, or its response was
lost) is not auto-retried; it is a human decision, surfaced as a `Paymob Audit Entry` a human
resolves. See [ADR-0018](decisions.md#adr-0018--a-lock-needs-an-in-progress-marker).

### Capture already in progress

**Functional:** A second click on Capture while the first request is still in flight is refused,
the same as Refund already in progress. A Refund or Void request against an attempt with a
capture in flight is refused too — the two must never race.

**Technical:** `api.request_capture` checks `attempt.capture_requested_at` immediately after the
row lock and permission check, exactly like `refund_requested_at` above, and is cleared only when
`paymob.processor.process_transaction` handles the verified `Capture` callback
(`processor.py`'s `if txn.event_kind == "Capture": attempt.capture_requested_at = None`) — never
by the outbound call's HTTP response. `request_refund` and `request_void` each also check
`attempt.capture_requested_at` and refuse if it is set, so a capture in flight cannot race a
refund or void of the same attempt. A stuck latch (the outbound call failed, or its response was
lost) is a human decision, same as a stuck refund marker — this is the "a lost capture callback is
unrecoverable automatically" case: only a human re-driving the capture, or reconciling directly
against Paymob, clears it. See
[ADR-0018](decisions.md#adr-0018--a-lock-needs-an-in-progress-marker).

### Missing callback (abandoned / lost)

**Functional:** If Paymob never calls back, we find out the status ourselves rather than guess —
whether that means the customer walked away, or a payment genuinely happened but the webhook that
should have told us about it never arrived.

**Technical:**
- `paymob.tasks.reconcile_pending_attempts`, scheduled every 15 minutes, selects `Pending` attempts
  whose `creation` and `last_polled_at` (or its absence) are both older than
  `Paymob Settings.stale_pending_minutes`, oldest first, capped at 50 attempts per run.
- Each selected attempt is locked (`for_update=True`) and re-checked for `state == "Pending"` — a
  webhook that landed between selection and now means there is nothing left to do.
  `settings.get_credential_set` resolves credentials using the **attempt's own frozen**
  `country`/`currency`/`mode`, not the site's current settings, because those can change while a
  checkout is open.
- The [Transaction Inquiry](#transaction-inquiry) call above answers one of three ways:
  - **A transaction is found** — stored via `paymob.transactions.store(source="Inquiry",
    hmac_verified=0)` and handed to `paymob.processor.process_transaction`, exactly as a webhook
    delivery would be. If the same transaction was already stored by a webhook that simply hasn't
    finished processing yet, the store's own duplicate-key guard returns `None` and the poller
    does nothing further — "the webhook already stored it; its own job owns the row." A successful
    recovery is recorded by the transaction, resulting state/Payment Entry, and application log;
    it creates no routine Audit Entry.
  - **No transaction, past `expires_at`** — the attempt moves to `Expired` without an Audit Entry.
    See [states.md](states.md#expired) and
    [ADR-0014](decisions.md#adr-0014--only-an-answered-inquiry-may-expire-an-attempt).
  - **No transaction, before `expires_at`** — nothing changes; the attempt is still within its
    window and stays `Pending` for the next run.
- A timeout, a `5xx`, or a repeated `401` leaves the attempt `Pending` — the poller never guesses
  from a failure to reach Paymob. `last_polled_at` is updated regardless of outcome, so one
  permanently-failing attempt cannot starve newer ones out of every bounded batch.
- Existing audit history is preserved in every case; no record is ever deleted.

### Request capture

**Functional:** A Refund Manager captures a verified authorization in full.

**Technical:** `api.request_capture` locks the attempt, checks its existing `refund` permission, uses only
the verified authorization's ID and integer amount (`paymob.transactions.verified_authorization` — an
`Auth` row, or a `Success` row retargeted to `Authorized` under
[ADR-0028](decisions.md#adr-0028--an-unprovable-capture-is-recorded-as-a-hold)), sets `capture_requested_at`,
writes `Capture Requested`, then calls `POST /api/acceptance/capture` once. A lost callback leaves the
latch set; no retry is automatic.
