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
