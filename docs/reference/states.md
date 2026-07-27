# States & Transitions

Payment/record **lifecycle states** and **review flags**. Format: see
[README.md](README.md). Governed by [../../rules/documentation.md](../../rules/documentation.md).

> **Two axes, do not fuse them.** A record has *one* lifecycle state (is the money confirmed?)
> and *separately* may carry a review flag (does a human need to look?). "Settled but flagged"
> is a valid combination. Never regress a lifecycle state to represent "needs review."

> `paymob.states.LEGAL` is this table's executable form, and `paymob.states.EVENT_TARGET` is the
> event-kind-to-target mapping just below. Change the table and the module together — a mismatch
> between the two means the docs describe a transition the code refuses, or the reverse.
> `Auth`/`Capture`/`Void` map to no target state yet: there is no `voided` state here, and the
> auth/capture flow ships in Phase 11. `paymob.processor` leaves those rows unprocessed
> (`processed = 0`) rather than inventing a transition, so Phase 11 can consume them.

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
- Raised by two code paths in `paymob.processor.process_transaction`: an illegal state
  transition (`states.IllegalTransition`, e.g. a `Success` callback arriving for an attempt
  already `Failed`) and an authentic amount/currency mismatch on a `Success` (Phase 07). Both
  paths write a `Paymob Audit Entry` — see
  [ADR-0009](decisions.md#adr-0009--audit-entries-are-submittable-and-immutable-a-resolution-is-an-append-via-supersedes).

## Event kinds (Paymob Transaction)

> These are **not** a third axis on top of the two above. A `Paymob Transaction` row is one
> append-only event received about a payment, not a record with its own lifecycle — `event_kind`
> never transitions, it is set once at insert and stays fixed forever. The lifecycle states above
> belong to the `Paymob Payment Attempt`; the event kinds below belong to the raw events that,
> from Phase 06 onward, drive that attempt's lifecycle state.

**Functional:** What kind of thing Paymob is telling us happened to a transaction — a plain
success, a decline, a wallet payment still settling, a reversal, or an authorization-only step.

**Technical:**
- Source of truth: `paymob.events.classify_event(obj)`, run on every authentic processed callback.
  There is no event-type field in Paymob's payload — the flags *are* the type, and reversal flags
  are read before `success`/`pending` because a refund callback also carries `success: true`.
- The seven stored `Select` values, checked in this order:

  | Value | Set when | Note |
  |---|---|---|
  | `Void` | `is_voided` | checked first, wins over every other flag |
  | `Refund` | `is_refunded` | also carries `success: true`; refund must be read before success |
  | `Capture` | `is_capture` | a captured authorization |
  | `Auth` | `is_auth` | authorization-only, not yet captured |
  | `Pending` | `pending` | wallet/kiosk in-flight; also carries `success: true` |
  | `Success` | `success` (and none of the above) | a completed payment |
  | `Decline` | none of the above flags set | the fallback |

- `event_kind` is half of the row's computed **name** (`"<paymob_transaction_id>:<event_kind>"`,
  see [ADR-0005](decisions.md#adr-0005--the-dedup-key-is-the-rows-own-primary-key-not-a-separate-unique-column))
  — the same transaction id can have one row per distinct kind (e.g. a `Success` row and a later
  `Refund` row for the same payment). `Refund` is the one exception to "never two rows of the
  same kind": its name also carries `refunded_amount_cents`, because Paymob resends the same
  parent transaction id for each cumulative partial refund — one row per distinct cumulative
  amount, not one row total.
