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

**Technical:** The timestamp of the last reconciliation inquiry. It is the one attempt field that
Phase 10 may update with `db_set`; money, status, and identifiers are never updated that way.

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
  `settings.get_credential_set()` and `settings.get_integration_ids()`; no single one of the three
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

**Technical:** Required Link to ERPNext Account, selected by a System Manager. Phase 08 reads it
onto the in-memory Payment Request before creating a Payment Entry.

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

**Technical:** Administrator-controlled Int, default 20 minutes. Phase 10 uses it to select
pending attempts for Transaction Inquiry.

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

### source (Paymob Transaction)

**Functional:** Where this event came from — did Paymob push it to us, or did we ask?

**Technical:** `Select`, `Webhook` or `Inquiry`, required. This phase always writes `Webhook`;
Phase 10's Transaction Inquiry poller writes `Inquiry` for rows it discovers itself.

### hmac_verified (Paymob Transaction)

**Functional:** Whether this event's authenticity was proven by a signature check.

**Technical:** `Check`, `1` on every row this phase writes (a webhook is only stored after HMAC
verification succeeds). The field exists for Phase 10's Transaction Inquiry rows, which carry no
signature to check and so are stored with this at `0`.

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

### event / description (Paymob Audit Entry)

**Functional:** What kind of thing went wrong, and a plain-language account of it a non-developer
can read without opening the code.

**Technical:** `event` is a required `Select` — `Illegal Transition`, `Amount Mismatch`, or
`Unattributed Payment` — set once by whichever branch of `paymob.processor` creates the entry.
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

**Technical:** `actor` is a plain `Data` field — the fully-qualified path of the system job for
every entry this phase writes (`paymob_integration.paymob.processor.process_transaction`);
Phase 11's human-triggered refund/void audit entries will carry `frappe.session.user` instead.
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
superseding record."
