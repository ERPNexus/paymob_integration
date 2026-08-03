# States & Transitions

Payment/record **lifecycle states** and **review flags**. Format: see
[README.md](README.md). Governed by [../../rules/documentation.md](../../rules/documentation.md).

> **Two axes, do not fuse them.** A record has *one* lifecycle state (is the money confirmed?)
> and *separately* may carry a review flag (does a human need to look?). "Settled but flagged"
> is a valid combination. Never regress a lifecycle state to represent "needs review."

> `paymob.states.LEGAL` is this table's executable form, and `paymob.states.EVENT_TARGET` is the
> event-kind-to-target mapping just below. Change the table and the module together — a mismatch
> between the two means the docs describe a transition the code refuses, or the reverse.
> `Auth` targets `authorized` and `Capture` targets `paid` (see `authorized` below,
> [ADR-0022](decisions.md#adr-0022--callback-facts-determine-authorization-state)). `Void` and
> `Refund` are handled from Phase 11 onward (see `voided`, `partially refunded`, and `refunded`
> below); a `Refund` row's target additionally depends on `has_parent_transaction`, not on the
> event kind alone — see the event-kind table.

## Lifecycle states

### pending

**Functional:** We're confirming the payment. The customer sees "We're confirming your payment."

**Technical:**
- Entered when: intention created and checkout started; no verified processed callback yet. An
  attempt created before a failed Paymob call is also pending and is resolved by the Phase 10 poller.
- Exits to: `paid` (verified success), `authorized` (verified auth-only hold), `failed` (verified
  decline), `expired` (abandoned + inquiry finds nothing).
- Terminal: no.

### authorized

**Functional:** An `Auth` callback puts a payment on hold without settling it. The customer sees
"Your payment has been authorized and is awaiting capture." Staff then capture or void it; only
capture can create the normal Payment Entry.

**Technical:**
- Entered when: an authentic processed callback reports an authorization-only `Auth` event
  (`is_auth`, no `is_capture`/`is_refunded`/`is_voided`).
- Exits to: `paid` (a verified, matched `Capture` callback), `voided` (a genuine void event). Never
  expires, fails, or refunds directly: an authorization is a real hold, while `expired` means no
  transaction ever existed.
- `capture_mode` (`Paymob Integration ID`, configured in Paymob Settings) selects which
  integrations a checkout offers — every enabled row for a country/currency/mode must agree (see
  [ADR-0027](decisions.md#adr-0027--capture-mode-is-a-paymob-settings-property)) — but it never
  gates *state*: only the callback's own flags do. See
  [ADR-0022](decisions.md#adr-0022--callback-facts-determine-authorization-state).
- Terminal: no.

### paid

**Functional:** Money is settled. The order can proceed; the ledger reflects payment. The
customer sees "Payment received. Thank you."

**Technical:**
- Entered when: an **authentic** (HMAC-verified) **processed callback** reports success **and**
  the amount matches the immutable intention snapshot — either a direct `Success` or a verified,
  amount-matched `Capture` of a prior `authorized` hold (`request_capture` sends the full
  authorized amount; a `Capture` reporting a different amount follows the same mismatch path and
  posts no Payment Entry — [ADR-0023](decisions.md#adr-0023--capture-is-full-amount-only)).
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
- Entered only by `paymob.tasks.reconcile_pending_attempts` (`tasks._expire_if_due`), and only
  when **both** hold: an *answered* Transaction Inquiry found no transaction for the reference
  (Paymob's HTTP 404), **and** `attempt.expires_at` has already passed. A 404 before `expires_at`
  leaves the attempt `Pending` — still checking, not abandoned.
- Never entered on a network error, a 5xx, or a repeated 401 — those propagate out of
  `tasks._inquire` as exceptions and leave the attempt `Pending` for the next scheduled run. Auth-
  token expiry and intention expiry share no code path — see
  [ADR-0014](decisions.md#adr-0014--only-an-answered-inquiry-may-expire-an-attempt).
- Audit history is preserved; the record is not deleted. Expiring writes one `Attempt Expired`
  `Paymob Audit Entry` (`needs_action = 0` — nothing for a human to act on, just a record of why).
- Terminal: yes.

### partially refunded

**Functional:** Some, but not all, of a settled payment was returned to the customer. The
customer sees "Part of this payment has been refunded."

**Technical:**
- Entered from `paid` on a genuine refund event whose running total is less than the amount
  charged; entered from itself again on a further partial refund (`paymob.states.check`'s
  `current == target` no-op — the state does not move, but the caller still posts the new delta).
- The running total lives on `Paymob Payment Attempt.refunded_amount_cents`, updated only from
  the signed child transaction's `amount_cents` — never from Paymob's unsigned cumulative
  `refunded_amount_cents` field. See [ADR-0017](decisions.md#adr-0017--a-refund-delta-comes-only-from-a-signed-child-transaction).
- Exits to: `refunded`, once the running total reaches the verified charged amount.
- Terminal: no.

### refunded

**Functional:** All settled money was returned to the customer. The customer sees "This
payment has been refunded."

**Technical:**
- Entered from `paid` (a single full refund) or from `partially refunded` (the running total
  reaches the verified charged amount) — never the reverse.
- Each refund event, full or partial, produces its own reversing ledger entry
  (`paymob.ledger.post_refund`) — it is a new, unallocated `Pay` Payment Entry, not a rollback or
  edit of the original. See [ADR-0016](decisions.md#adr-0016--reversals-are-on-account-pay-payment-entries).
- Terminal: yes.

### voided

**Functional:** A paid or authorized attempt was cancelled and any money that moved was returned
in full. The customer sees "This payment has been voided."

**Technical:**
- Entered from `paid` or `authorized`, on a genuine, separately-signed **void event**. There is no
  partial void.
- If no Payment Entry was ever posted for the attempt — always true for an `authorized` void
  (never had money posted), and also true for a `paid` attempt whose Payment Entry was blocked by
  an unresolved amount mismatch — the state still moves to `voided` and `paymob.ledger.post_refund`
  posts nothing, recorded as a `Nothing To Reverse` audit entry (`needs_action = 0`). The delta is
  keyed on whether `attempt.payment_entry` is actually set, never on the state alone.
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
- A `Refund` row's effect on the lifecycle depends on `has_parent_transaction`, not on
  `event_kind` alone: Paymob sends **two** callbacks per refund — a child row (`has_parent_
  transaction = true`, its own `id`, `amount_cents` = the refund delta, HMAC-signed) that is the
  money-bearing message, and a parent re-send (`has_parent_transaction = false`, the *original*
  charge's `id`, a growing unsigned `refunded_amount_cents`) that cannot prove a refund delta —
  stored, marked processed, never posted. The re-send is only surfaced as `Refund Requires Review`
  when its cumulative total outruns what the attempt has posted, which is the one case where it
  says something the child transactions did not.
  See
  [ADR-0017](decisions.md#adr-0017--a-refund-delta-comes-only-from-a-signed-child-transaction).
