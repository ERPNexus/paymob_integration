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
| `Failed` | Verified decline | None |
| `Expired` | Answered inquiry finds no transaction after expiry | None |

A state never moves backwards. `needs_human_attention` is separate from lifecycle state: an amount
mismatch, duplicate payment, illegal transition, or unsupported Paymob event is audited for review
without creating a Payment Entry.

## Event kinds

`Paymob Transaction.event_kind` is immutable evidence, not a lifecycle state. Events are classified
in this order: `Refund`, `Unsupported`, `Pending`, `Success`, `Decline`.

`Unsupported` covers signed `is_auth`, `is_capture`, or `is_voided` flags. Their signed, redacted
facts are stored and one `Unsupported Paymob Event` audit entry is raised, but they never change an
attempt state or the ledger. The fields remain in the HMAC contract only.

`Refund` uses the signed child transaction amount as the posted delta. Parent re-sends with a
cumulative refund total are stored but do not create money movement.
