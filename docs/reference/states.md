# States & Transitions

Payment Attempt lifecycle states and review flags. `paymob.states.LEGAL` is the executable source
of these transitions.

## Lifecycle states

| State | Entered by | Legal exits |
|---|---|---|
| `Pending` | Checkout begins; pending callback | `Paid`, `Failed`, `Expired` |
| `Paid` | Verified, exact-amount `Success`; one Payment Entry is posted | `Partially Refunded`, `Refunded` |
| `Partially Refunded` | Verified signed refund delta below the original charge | `Refunded` |
| `Refunded` | Verified signed refunds reach the original charge | None |
| `Failed` | Verified decline | `Paid` from a later verified, exact-amount `Success` for the same still-valid Paymob checkout |
| `Expired` | Answered inquiry finds no transaction after expiry | None |

A decline records the latest failed try, but a still-valid Paymob intention may later produce a
verified, exact-amount `Success`; only then may `Failed` move to `Paid`. Immutable Paymob Transaction
rows retain both events. All other state changes remain forward-only.

`needs_human_attention` is separate from lifecycle state: an amount mismatch, duplicate payment,
illegal transition, or unsupported Paymob event is audited for review without creating a Payment Entry.

## Event kinds

`Paymob Transaction.event_kind` is immutable evidence, not a lifecycle state. Events are classified
in this order: `Refund`, `Unsupported`, `Pending`, `Success`, `Decline`.

`Unsupported` covers signed `is_auth`, `is_capture`, or `is_voided` flags. Their signed, redacted
facts are stored and one `Unsupported Paymob Event` audit entry is raised, but they never change an
attempt state or the ledger. The fields remain in the HMAC contract only.

`Refund` uses the signed child transaction amount as the posted delta (ADR-0017). Parent re-sends
carry a cumulative refund total that is never HMAC-signed, so it never posts money. When that total
already matches what this app has posted, the re-send is routine evidence: no audit entry, no state
or refund-total change, no flag. When it outruns what has been posted — a refund happened at Paymob
whose signed child transaction never reached the webhook — the attempt is flagged for human
attention and a `Refund Requires Review` audit entry is raised; still no money is posted
automatically.
