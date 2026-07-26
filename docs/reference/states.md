# States & Transitions

Payment/record **lifecycle states** and **review flags**. Format: see
[README.md](README.md). Governed by [../../rules/documentation.md](../../rules/documentation.md).

> **Two axes, do not fuse them.** A record has *one* lifecycle state (is the money confirmed?)
> and *separately* may carry a review flag (does a human need to look?). "Settled but flagged"
> is a valid combination. Never regress a lifecycle state to represent "needs review."

## Lifecycle states

### pending

**Functional:** We're confirming the payment. The customer sees "We're confirming your payment."

**Technical:**
- Entered when: intention created and checkout started; no verified processed callback yet. An
  attempt created before a failed Paymob call is also pending and is resolved by the Phase 10 poller.
- Exits to: `paid` (verified success), `failed` (verified decline), `expired` (abandoned + inquiry finds nothing).
- Terminal: no.

### paid

**Functional:** Money is settled. The order can proceed; the ledger reflects payment. The
customer sees "Payment received. Thank you."

**Technical:**
- Entered when: an **authentic** (HMAC-verified) **processed callback** reports success **and**
  the amount matches the immutable intention snapshot.
- Exits to: `refunded` (a genuine, separately-signed refund event). Does **not** exit to `failed`.
- Terminal: effectively yes, except a real refund.

### failed

**Functional:** The payment did not go through. The customer may retry (a retry is a fresh
attempt). The customer sees "This payment did not go through. You can try again."

**Technical:**
- Entered when: an authentic processed callback reports a decline.
- A retry uses a **new** intention, special reference, Paymob order ID, and client secret — it
  does not transition this record back to `pending`.
- Terminal: yes for this attempt.

### expired

**Functional:** The customer never completed checkout and the window closed. Nothing was charged.
The customer sees "This payment link has expired."

**Technical:**
- Entered when: no callback arrived and a scheduled **Transaction Inquiry** confirms no completion.
- Audit history is preserved; the record is not deleted.
- Terminal: yes.

### refunded

**Functional:** Previously settled money was returned to the customer. The customer sees "This
payment has been refunded."

**Technical:**
- Entered from `paid` only, on a genuine, separately-signed **refund event**.
- Produces its own reversing ledger entry — it is a new event, not a rollback of the original.
- Terminal: yes.

## Review flags (orthogonal to lifecycle state)

### needs_human_attention

**Functional:** Money looks settled, but something is off — a human must review before we treat
it as final. The customer still sees the normal "payment received" result.

**Technical:**
- Raised when: an authentic callback contradicts expectations — e.g. amount ≠ intention snapshot,
  or a late/anomalous status (a `failed` arriving days after `paid`).
- Effect: **blocks automatic Payment Entry creation**; queues the record for manual review.
- **Does NOT change the lifecycle state.** The record stays `paid` (or whatever it was); this is
  a flag *alongside* it. Resolve by human decision → keep `paid`, or move to `refunded`, etc.
- See decision [ADR-0003](decisions.md#adr-0003--authentic-amount-mismatch-is-audited-never-auto-posted).
