# Fields

DocType fields that carry meaning. For each: what it holds, its **source of truth**, validation,
and mutability. Governed by [../../rules/documentation.md](../../rules/documentation.md).

### state (lifecycle)

**Functional:** Where this payment is in its life — pending, paid, failed, expired, or refunded.

**Technical:**
- Source of truth: ERPNext, driven by verified Paymob events (see [states.md](states.md)).
- Validation: only legal transitions allowed; never regressed to represent "needs review."

### expected_amount_cents (snapshot)

**Functional:** The amount we expected to be paid, frozen at checkout time.

**Technical:**
- Source of truth: ERPNext database at **Create Intention** time (never the browser).
- Stored as a `Long Int` in the currency's minor units and immutable after creation. Every callback
  amount is compared against *this*, not a re-read total.
- A mismatch triggers [ADR-0003](decisions.md#adr-0003--authentic-amount-mismatch-is-audited-never-auto-posted).

### needs_human_attention (review flag)

**Functional:** Marks a settled-but-suspicious record for manual review.

**Technical:**
- Boolean flag, **orthogonal** to `state`. See [states.md](states.md#needs_human_attention).
- Raised by `paymob.processor._refuse` (an illegal transition — the state itself is left
  unchanged, e.g. a `Success` after `Failed` stays `Failed`) and by `paymob.processor.
  process_transaction`'s amount/currency check on a `Success` (Phase 07, state still advances to
  `Paid`). Both paths use `attempt.save(ignore_permissions=True)`, never `db_set`.

### special_reference / merchant_order_id

**Functional:** Our own reference that ties a Paymob checkout back to the originating ERPNext record.

**Technical:**
- Source of truth: ERPNext (derived from `Payment Request.name`). Sent to Paymob at intention creation.
- Distinct from Paymob's signed `order.id` — do not conflate the two.

### paymob_intention_id / paymob_order_id / paymob_transaction_id

**Functional:** Paymob's own identifiers for the intention, the order, and (once paid) the transaction.

**Technical:**
- Source of truth: **Paymob** (returned in responses/callbacks). Stored durably for correlation and inquiry.
- `paymob_transaction_id` exists only after a transaction occurs; an abandoned checkout has none.

### client_secret (transient)

**Functional:** A short-lived token that unlocks one checkout session in the browser.

**Technical:**
- Source of truth: Paymob (intention response). Browser-exposed and single-session (see [ADR-0002](decisions.md#adr-0002--server-only-credentials-never-reach-the-browser)).
- Transient — not a long-lived credential; do not treat as a read/inquiry key.

### last_polled_at

**Functional:** When we last checked with Paymob to see what really happened to this payment.

**Technical:** The timestamp of the last reconciliation inquiry, set by `tasks._reconcile`'s
`finally` block — it runs whether the inquiry succeeded, failed, or found nothing, so one
permanently-failing attempt cannot starve newer ones out of every bounded batch. It is the one
attempt field Phase 10 updates with `db_set`; money, status, and identifiers are never updated
that way.

### payment_entry (Paymob Payment Attempt)

**Functional:** Which ERPNext Payment Entry this attempt's money landed in, once it has.

**Technical:** Link to Payment Entry, blank until `paymob.ledger.post_payment` posts one. Set with
`attempt.save(ignore_permissions=True)`, never `db_set` — it is money-adjacent, not bookkeeping.
See [ADR-0008](decisions.md#adr-0008--the-in-memory-payment_account-assignment-and-a-post-hoc-amount-check).

### contact_email (Paymob Payment Attempt)

**Functional:** The payer receives status and retry notifications at the address used for checkout.

**Technical:** Read-only `Data` with `Email` options, populated from the linked document's
`contact_email` or the Payment Request's `email_to`, the same fallback sent to Paymob as billing data.
It stores no additional source of customer data and is never logged.

### refunded_amount_cents (Paymob Payment Attempt)

**Functional:** How much of this payment has actually been posted back to the customer so far.

**Technical:**
- `Long Int`, read-only, integer minor units. Blank (`NULL`) on rows that predate this field —
  every reader treats it as `(attempt.refunded_amount_cents or 0)`, never a bare truthiness or
  equality check on the column itself. This is the app's **own** running
  total of what `paymob.ledger.post_refund` has posted — it is written only from a signed child
  transaction's `amount_cents` (`processor.process_transaction`), never from Paymob's unsigned
  cumulative `refunded_amount_cents` on the transaction row. See
  [ADR-0017](decisions.md#adr-0017--a-refund-delta-comes-only-from-a-signed-child-transaction).
- Caps both directions of a refund: `api._verified_charge` (the outbound request) and
  `processor`'s refund guard (the inbound callback) both read
  `paymob.transactions.verified_charge` for the amount actually charged, and compare it
  against this running total — the same source in both places, so the two can never disagree
  about how much remains refundable.

### refund_requested_at (Paymob Payment Attempt)

**Functional:** Whether a refund or void is currently in flight for this attempt, so a second
click cannot fire a second outbound call.

**Technical:**
- `Datetime`, read-only, blank when no refund/void is in progress. Set with `attempt.db_set(...)`
  — the documented `db_set` exception, bookkeeping not money — inside the same `for_update=True`
  lock `api.request_refund`/`api.request_void` already hold, so it becomes visible to a second
  concurrent request exactly when the first commits. See
  [ADR-0018](decisions.md#adr-0018--a-lock-needs-an-in-progress-marker).
- Cleared in exactly one place: `processor.process_transaction`, once the verified refund/void
  callback lands and `paymob.ledger.post_refund` has run. A network error on the outbound call
  leaves it set on purpose — a lost response does not prove the request failed, so re-issuing is
  a human decision (`rules/payments.md` rule 13). A refund arriving with no marker set is
  legitimate too (a merchant refunded from the Paymob dashboard directly); it posts normally.

### enabled (Paymob Settings, Paymob Credential Set, Paymob Integration ID)

**Functional:** Three separate on/off switches, at three different levels. `Paymob Settings.enabled`
turns Paymob **off for the whole site**. A credential-set row's `enabled` turns off **one country's
credentials**. An integration-ID row's `enabled` turns off **one payment method**. Switching one off
does not switch the others off.

**Technical:**
- `Paymob Settings.enabled` defaults to `0` (off) — an administrator must turn it on deliberately.
- `Paymob Credential Set.enabled` and `Paymob Integration ID.enabled` default to `1` (on), since a
  row is normally added because it is ready to use.
- Code that resolves credentials or payment methods must check the relevant `enabled` flag at every
  level it applies to — a disabled row must never be silently skipped *or* silently used.

### country / currency (Paymob Credential Set, Paymob Integration ID)

**Functional:** Which country and which currency this row of credentials, or this row of payment
methods, is for. Paymob keeps a fully separate account per country — the keys and payment methods
for Egypt cannot be reused for Saudi Arabia.

**Technical:**
- `country`: free-text `Data` field (e.g. `Egypt`, `Saudi Arabia`) — matched against the Paymob
  region the credential set belongs to. Required on both DocTypes. Checkout resolves this from the
  Payment Request's company country, not the customer's billing address.
- `currency`: `Link` to ERPNext's `Currency` DocType (e.g. `EGP`, `SAR`) — required on both. The
  currency of a Payment Request must match a credential set and integration ID with the same
  `country` + `currency` + `mode` combination, or there is nothing to pay with.
- The **combination** of `country` + `currency` + `mode` is the lookup key used by
  `settings.get_credential_set()` and `settings.resolve_integrations()`; no single one of the three
  fields is unique on its own.

### base_url (Paymob Credential Set)

**Functional:** The web address of the Paymob servers this credential set talks to.

**Technical:**
- `Data` field, required. Paymob runs a **separate deployment per region**
  (e.g. `https://accept.paymob.com/` for Egypt, `https://ksa.paymob.com/` for Saudi Arabia) — using
  the wrong `base_url` for a country's keys fails every request.
- Same `base_url` serves both Test and Live mode; only the keys and integration IDs differ between
  modes, not the URL.

### public_key (Paymob Credential Set)

**Functional:** The one Paymob key that is safe to send to the customer's browser. It identifies
your account to Paymob's hosted checkout page — it cannot be used to move money.

**Technical:**
- `Data` field, required, mode-specific (`pk_test_...` / `pk_live_...`). Unlike `secret_key`,
  `api_key`, and `hmac_secret`, this field is **not** a Password fieldtype, because it is meant to
  reach the browser — it is embedded in the Unified Checkout URL / Pixel initialization.
- Never confuse with `client_secret` (see above), which is per-intention and short-lived; `public_key`
  is a long-lived, per-credential-set identifier.

### mode (Paymob Settings, Paymob Credential Set, Paymob Integration ID)

**Functional:** Switches between Paymob's **test** environment (fake money, for building and QA)
and **live** environment (real money, real customers).

**Technical:**
- `Paymob Settings.mode` is the site-wide switch — the value credential resolution matches against.
- Each `Paymob Credential Set` and `Paymob Integration ID` row also carries its own `mode`, because a
  merchant keeps separate Test and Live rows side by side rather than overwriting one with the other.
- A `Test` key paired with a `Live` integration ID (or vice versa) is a configuration error Paymob's
  API rejects — the selected `mode` must match on **both** the credential set and the integration ID
  used for a given payment. Missing Live credentials never fall back to Test.

### payment_method / integration_id (Paymob Integration ID)

**Functional:** One row of this table represents one way a customer can pay (for example "card
payments in EGP" or "mobile wallet"), and which Paymob configuration handles it.

**Technical:**
- `payment_method`: `Data` field, required — a short label chosen by whoever configures the row
  (e.g. `Card`, `Wallet`); it is descriptive only and is not sent to Paymob.
- `integration_id`: `Data` field, required — the **numeric ID Paymob assigns** to one payment-method
  configuration in its dashboard (Developers → Payment Integrations). This is the value sent in the
  Create Intention request's `payment_methods` array.
- Do not confuse this `integration_id` field (Paymob's number, e.g. `"12345"`) with the DocType name
  `Paymob Integration ID` (the child table row that holds it) — same words, different things.

### payment_account (Paymob Credential Set)

**Functional:** The clearing account where payments for this configuration will land.

**Technical:** Required Link to ERPNext Account, selected by a System Manager. `paymob.ledger.
post_payment` reads it onto the in-memory Payment Request before creating a Payment Entry. See
[ADR-0008](decisions.md#adr-0008--the-in-memory-payment_account-assignment-and-a-post-hoc-amount-check).

### secret_key / api_key / hmac_secret (Paymob Credential Set)

**Functional:** The server-only Paymob keys used to create payments, authenticate inquiries, and
verify callbacks.

**Technical:** Password fields sourced from the Paymob dashboard, read only with `get_password()`,
and replaced on key rotation. Test Connection validates the API key; saving never calls Paymob.

### intention_expiration_seconds (Paymob Settings)

**Functional:** How long a hosted checkout is valid.

**Technical:** Administrator-controlled Int, default 3600 seconds. Phase 02 uses it when creating
a Paymob intention.

### stale_pending_minutes (Paymob Settings)

**Functional:** How long a pending payment waits before reconciliation checks it.

**Technical:** Administrator-controlled Int, default 20 minutes. `tasks.reconcile_pending_attempts`
subtracts this from now to compute the selection cutoff: a `Pending` attempt is eligible once both
its `creation` and its `last_polled_at` (or the absence of one) are older than that cutoff.

### send_payment_link_email / send_status_emails (Paymob Settings)

**Functional:** Two switches for the app's outgoing mail. The first decides whether a submitted
Payment Request emails the payer a Paymob checkout link. The second turns the whole set of Paymob
alerts — payment received, payment failed, link expired, refund issued, refund or void activity,
audit entry needs review, poller recovered — on or off in one place, instead of asking a merchant
to find and edit seven records in the Notification list.

**Technical:** Both are Checks defaulting to `1`. `payment_request.prepare_payment_email` reads
`send_payment_link_email` on `validate` and either sets a signed `payment_url` or sets
`mute_email = 1` ([ADR-0024](decisions.md#adr-0024--the-payment-link-email-is-decided-at-validate)).
`send_status_emails` is applied by `PaymobSettings.on_update` through
`notifications.sync_enabled`, which flips `enabled` on the seeded records **by name** — a merchant's
own Notification on the same DocType is never touched — and then clears Frappe's notification cache.
Existing sites are backfilled to `1` by the idempotent `default_send_status_emails` patch, so the
setting never reads as "off by omission".

### name / event_key (Paymob Transaction)

**Functional:** The same webhook delivered twice never creates two records.

**Technical:**
- Source of truth: `PaymobTransaction.autoname()`, which sets `self.name =
  f"{paymob_transaction_id}:{event_kind}"` — except for `Refund`, which appends
  `:{refunded_amount_cents}` because Paymob resends the same parent transaction id for each
  cumulative partial refund. There is no separate `event_key` field — the document's own primary
  key **is** the dedup key, so the guard is a database constraint, not an `if`. See
  [ADR-0005](decisions.md#adr-0005--the-dedup-key-is-the-rows-own-primary-key-not-a-separate-unique-column).
- A duplicate delivery raises `frappe.DuplicateEntryError` on `insert()`; `webhooks._store`
  catches exactly that exception and only that one.

### event_kind (Paymob Transaction)

**Functional:** What kind of event this row records — see
[states.md](states.md#event-kinds-paymob-transaction) for the full list and classification order.

**Technical:** `Select`, required, set once by `events.classify_event(obj)` at insert time and
never changed afterward — an append-only record has no field that transitions.

### paymob_transaction (Paymob Audit Entry)

**Functional:** The exact gateway event behind an audit entry, available from the event's Desk
form under **Connections**.

**Technical:** Read-only Link to `Paymob Transaction`, set by `paymob.audit.record`. The external
`paymob_transaction_id` remains for gateway correlation; it can identify multiple local event rows
(for example, a partial refund sequence), while this link identifies one exact stored event.

### source (Paymob Transaction)

**Functional:** Where this event came from — did Paymob push it to us, or did we ask?

**Technical:** `Select`, `Webhook` or `Inquiry`, required, both written by the single writer
`paymob.transactions.store` ([ADR-0015](decisions.md#adr-0015--one-writer-for-the-paymob-transaction-log)).
`webhooks.processed_callback` passes `source="Webhook"`; `tasks._hand_off` (the reconciliation
poller) passes `source="Inquiry"` for rows it discovers itself.

### hmac_verified (Paymob Transaction)

**Functional:** Whether this event's authenticity was proven by a signature check.

**Technical:** `Check`. `1` on every `Webhook` row — a webhook is only stored after HMAC
verification succeeds. `0` on every `Inquiry` row from the reconciliation poller: a Transaction
Inquiry response carries no signature to check; its authenticity guarantee is the authenticated
Bearer channel plus the fact that the poller asked about a reference it minted itself.

### processed (Paymob Transaction)

**Functional:** Whether this event has been used yet to drive the payment's lifecycle state.

**Technical:** `Check`, defaults to `0`. `webhooks.processed_callback` enqueues
`paymob.processor.process_transaction` after every newly-stored row's commit; that job flips this
to `1` with `txn.db_set("processed", 1)` — the one documented `db_set` exception on this DocType,
alongside `Paymob Payment Attempt.last_polled_at`, because it is bookkeeping, not money. It stays
`0` for `Auth`, `Capture`, and `Void` rows, which map to no lifecycle state yet (Phase 11) and are
deliberately left for that phase to pick up.

### raw_payload (Paymob Transaction)

**Functional:** The reconciliation-relevant part of the event as Paymob sent it, kept for audit
— never surfaced in a log line, and never a second copy of customer personal data.

**Technical:** `Code`, `frappe.as_json(webhooks._redact(obj))`. `_redact` keeps an **allowlist**
of transaction/amount/status fields (never the whole `obj`) plus `order` trimmed to
`id`/`merchant_order_id` and `source_data` trimmed to `type`/`sub_type`/`pan` (Paymob's masked
last-four, allowed under `rules/stored-payment-data.md`). Real Paymob payloads carry
`billing_data` and similar customer-identity blocks beyond what this app uses; those are dropped
before storage. `rules/logging.md` forbids logging the complete webhook payload; this field is
the durable record instead, readable only by System Manager / Accounts Manager per the DocType's
permissions. No role has delete on this DocType — see
[audit-trail.md](../../rules/audit-trail.md) on immutability.

### currency (Paymob Transaction)

**Functional:** The currency Paymob reported for this specific event.

**Technical:** `Data`, not `Link` — unlike `Paymob Payment Attempt.currency`. This value comes
from an inbound, unverified-against-ERPNext fact; a `Link` field would throw (and the webhook
would 500, and Paymob would retry forever) the moment Paymob reports a currency ERPNext has no
`Currency` row for. Comparing it against the attempt's `currency` (a business decision) is Phase
06's job, not this DocType's.

### has_parent_transaction (Paymob Transaction)

**Functional:** Distinguishes the two callbacks a single Paymob refund produces — this one, or
the original charge being re-announced with a growing total.

**Technical:** `Check`, read-only, written by `paymob.transactions.store` from the signed
`has_parent_transaction` payload field. `true` on the child refund row (own `id`, `amount_cents`
= the delta) — the money-bearing message. `false` on the parent re-send (the *original* charge's
`id`) — never enough evidence to post. `processor.process_transaction` marks it processed and, when
its cumulative `refunded_amount_cents` outruns the attempt's posted total, writes a
`Refund Requires Review` audit entry; a matching total is consumed quietly, since the re-send
arrives on every refund including the ones that posted correctly.
See [ADR-0017](decisions.md#adr-0017--a-refund-delta-comes-only-from-a-signed-child-transaction).

### refunded_amount_cents (Paymob Transaction)

**Functional:** Paymob's own running total of how much of the original charge has been refunded
so far, as reported on this event.

**Technical:** `Long Int`, read-only. **Unsigned and never used for money** —
`hmac_verify.PROCESSED_CALLBACK_FIELDS` does not include this field, so an attacker who reaches
the guest webhook endpoint cannot forge the HMAC but could still send an arbitrary value here
without invalidating the signature. Every refund posting reads the child transaction's own
signed `amount_cents` instead (see [refunded_amount_cents (Paymob Payment Attempt)](#refunded_amount_cents-paymob-payment-attempt)
above); this field is stored for correlation with Paymob's dashboard only, and
`transactions.event_key` appends it to a `Refund` row's own name so each distinct cumulative
total gets its own row.

### event / description (Paymob Audit Entry)

**Functional:** What requires human attention, or which user requested a capture, refund, or void,
with a plain-language account a non-developer can read without opening the code.

**Technical:** `event` is a required `Select`. Active exception events are `Illegal Transition`,
`Amount Mismatch`, `Unattributed Payment`, `Refund Requires Review`, `Duplicate Payment`,
`Capture Not Requested`, and `Authorization Unconfirmed`; each has `needs_action = 1`. Active
accountability events are `Capture Requested`, `Refund Requested`, and `Void Requested`; they are
written synchronously inside the outbound whitelisted call before Paymob is contacted and carry
`txn=None` because no transaction row exists yet. `Poller Recovery`, `Attempt Expired`, and
`Nothing To Reverse` remain valid Select options only so historical records stay readable; new
rows are no longer created for those routine outcomes. `Capture Not Requested` (`needs_action = 1`,
and it sets `Paymob Payment Attempt.needs_human_attention`) is written by `paymob.processor` when a
verified callback moves an `authorize_only` attempt to `Paid` while `capture_requested_at` is
empty — Paymob captured a hold nobody asked it to capture, so the Integration ID is not configured
for authorization holds in Paymob's own dashboard. The Payment Entry is still posted; the money is
real and verified ([ADR-0026](decisions.md#adr-0026--a-hold-paymob-captures-anyway-is-posted-and-audited)).
`Authorization Unconfirmed` (`needs_action = 1`, and it sets `needs_human_attention`) is written by
`paymob.processor` for the opposite, unprovable case: a plain `Success` callback on an
`authorize_only` attempt with none of the reversal/capture/auth flags signed. Unlike
`Capture Not Requested`, no Payment Entry is posted — the attempt is retargeted to `Authorized`
instead of `Paid`, because nothing signed proves the card was actually charged
([ADR-0028](decisions.md#adr-0028--an-unprovable-capture-is-recorded-as-a-hold)).
`description` is always built with `_()` and named values (never string concatenation), per
[`rules/translation.md`](../../rules/translation.md).

### expected_amount_cents / expected_currency / received_amount_cents / received_currency (Paymob Audit Entry)

**Functional:** The two numbers (and their currencies) being compared when an entry is about an
amount mismatch — blank for an `Illegal Transition` entry, which isn't about amounts at all.

**Technical:** Written only by `paymob.processor.process_transaction`'s mismatch branch (Phase 07):
`expected_*` comes from `attempt.expected_amount_cents` / `attempt.currency` (the immutable
checkout-time snapshot), `received_*` from `txn.amount_cents` / `txn.currency` (the authentic
callback). `Long Int`, never `Currency` — these are minor units, not a display amount. See
[ADR-0003](decisions.md#adr-0003--authentic-amount-mismatch-is-audited-never-auto-posted).

### actor / occurred_at (Paymob Audit Entry)

**Functional:** Who or what caused this record to exist, and when.

**Technical:** `actor` is a plain `Data` field. For the code-triggered event kinds it is the
fully-qualified path of the caller that invoked `paymob.audit.record`, passed explicitly as a
required parameter ([ADR-0012](decisions.md#adr-0012--the-audit-writer-moved-to-its-own-module)):
`paymob_integration.paymob.processor.process_transaction` for `Illegal Transition`,
`Amount Mismatch`, `Unattributed Payment`, `Refund Requires Review`, `Capture Not Requested`, and
`Authorization Unconfirmed`;
`paymob_integration.paymob.ledger.post_payment` for `Duplicate Payment`. For the three
human-triggered capture/refund/void events, `api.request_capture`/`request_refund`/`request_void`
pass `frappe.session.user` instead — the person who clicked the button, not a module path.
`occurred_at` is `transaction.received_at` when the entry is tied to a stored transaction, falling
back to `frappe.utils.now_datetime()` otherwise — deliberately **system-timezone**, matching
`Paymob Transaction.received_at`, not literal UTC; two datetime conventions in one app would be a
reconciliation bug waiting to happen.

### supersedes / needs_action (Paymob Audit Entry)

**Functional:** How a resolved issue is recorded without ever editing the original record, and
how the "still needs a look" list is built.

**Technical:** `supersedes` is a self-referencing `Link`, set only when a later entry resolves an
earlier one — a correction is always a new row, never an edit (see
[ADR-0009](decisions.md#adr-0009--audit-entries-are-submittable-and-immutable-a-resolution-is-an-append-via-supersedes)).
`needs_action` drives the `Paymob Open Audit Entries` report, which excludes any entry named in
another submitted entry's `supersedes` field — a list filter alone cannot express "has no
superseding record." The workspace's **Needs Attention** card opens the filtered Audit Entry list
so its Description is immediately visible; its native count includes superseded entries, while
the report is the canonical open-item count.

### Capture controls

**Functional:** Staff can see an authorization awaiting capture and cannot double-submit it.
Whether a checkout charges immediately or holds is set once, in Paymob Settings — never on the
Payment Request, and never by the payer.

**Technical:** `Paymob Payment Attempt.capture_requested_at` is a nullable, read-only `Datetime`, set under
the request lock and cleared only by a verified Capture callback. `Paymob Integration ID.capture_mode`
must match how that Integration ID is configured in Paymob's own dashboard, and every *enabled* row
sharing a `(country, currency, mode)` must agree on it — a mixed group is refused both at save
(`Paymob Settings.validate`) and at checkout (`paymob.settings.resolve_integrations`), since Paymob's
hosted checkout would otherwise let the payer pick the outcome by which button they click. `_checkout`
calls `resolve_integrations(country, currency)` to get that one agreed mode plus every enabled ID in
the group. See [ADR-0027](decisions.md#adr-0027--capture-mode-is-a-paymob-settings-property). It still
never determines attempt state — verified callback flags do that alone
([ADR-0022](decisions.md#adr-0022--callback-facts-determine-authorization-state)).

### authorize_only (Paymob Payment Attempt)

**Functional:** Records whether this specific checkout attempt was configured for a hold, even if
Paymob Settings is later reconfigured to auto-capture.

**Technical:** A read-only `Check`, snapshotted from the capture mode `_checkout` resolved via
`settings.resolve_integrations` at `_create_attempt` time — the same reason `mode` and `country`
are snapshotted there. Bookkeeping only: it never gates a state transition
([ADR-0022](decisions.md#adr-0022--callback-facts-determine-authorization-state)). `api._checkout`'s
pending-attempt reuse path only reuses an attempt whose stored `authorize_only` matches the mode
currently configured — a merchant who reconfigures Paymob Settings after minting a payer link gets a
fresh attempt, not the stale one. See
[ADR-0027](decisions.md#adr-0027--capture-mode-is-a-paymob-settings-property).
