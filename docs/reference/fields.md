# Fields

DocType fields that carry meaning. For each: what it holds, its **source of truth**, validation,
and mutability. Governed by [../../rules/documentation.md](../../rules/documentation.md).

> Field names below are **provisional** and will be reconciled with the actual DocType schema as
> it is built. The *role* of each field is the stable part; the exact `fieldname` is lookup detail.

### state (lifecycle)

**Functional:** Where this payment is in its life — pending, paid, failed, expired, or refunded.

**Technical:**
- Source of truth: ERPNext, driven by verified Paymob events (see [states.md](states.md)).
- Validation: only legal transitions allowed; never regressed to represent "needs review."

### expected_amount (snapshot)

**Functional:** The amount we expected to be paid, frozen at checkout time.

**Technical:**
- Source of truth: ERPNext database at **Create Intention** time (never the browser).
- **Immutable** after creation. Every callback amount is compared against *this*, not a re-read total.
- A mismatch triggers [ADR-0003](decisions.md#adr-0003--authentic-amount-mismatch-is-audited-never-auto-posted).

### needs_human_attention (review flag)

**Functional:** Marks a settled-but-suspicious record for manual review.

**Technical:**
- Boolean flag, **orthogonal** to `state`. See [states.md](states.md#needs_human_attention).

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
  region the credential set belongs to. Required on both DocTypes.
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
