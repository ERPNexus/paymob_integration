# Decisions (ADRs)

## ADR-0001 — Verified inbound facts are the only ledger authority

Payment Entries are created only by the shared ledger path after a verified processed callback or
Transaction Inquiry result. Outbound HTTP responses are never evidence of money movement.

## ADR-0003 — Authentic amount mismatches are audited, never auto-posted

The callback amount and currency must match the immutable checkout snapshot. A mismatch creates
review work and no Payment Entry.

## ADR-0004 — Lifecycle state belongs to Payment Attempt

Each checkout attempt has its own state, allowing a failed attempt and a later retry to coexist
without writing Payment Request status directly.

## ADR-0005 — Transaction event keys deduplicate delivery

The append-only transaction's event key is unique. A duplicate is acknowledged successfully without
a new event, state change, audit entry, or ledger write.

## ADR-0006 — The processed callback is the only guest endpoint

The callback verifies HMAC before document access. Other money-affecting interfaces require normal
Frappe permission checks.

## ADR-0007 — Persist before acknowledging

The callback returns HTTP 200 only after its event is durable. Unexpected persistence failures remain
non-2xx so Paymob may retry.

## ADR-0008 — One Payment Entry writer

`paymob.ledger.post_payment` is the sole receive-entry writer and delegates allocation to ERPNext.
`paymob.ledger.post_refund` writes signed refund deltas as reversal entries.

## ADR-0009 — Audit entries are immutable

Audit records are submitted facts. Resolution is a new entry that references `supersedes` rather
than an edit or deletion.

## ADR-0014 — Only an answered inquiry may expire an attempt

Network errors and unconfirmed reads leave a pending attempt unchanged. Expiry requires an answered
inquiry with no transaction after the checkout expiry time.

## ADR-0016 — Refund reversals are on-account Pay Payment Entries

A verified refund delta creates a separate Pay Payment Entry. The original incoming Payment Entry
is never edited or cancelled.

## ADR-0017 — Refund deltas come from signed child transactions (superseded by ADR-0032)

Only the signed child transaction amount can post a refund delta. Unsigned cumulative parent totals
are stored for evidence but do not move the ledger.

**Superseded 2026-08-06.** No standalone/hosted-checkout card refund on `capital` ever sent a child
transaction — two independent live refunds (`510236778`, `510198387`) each arrived as exactly one
parent re-send, so every real refund landed in "needs review" forever. ADR-0032 replaces the "wait
for a child transaction" remedy while keeping this ADR's underlying distrust of the unsigned
`refunded_amount_cents` field intact.

## ADR-0018 — A refund lock needs an in-progress marker

The refund request holds the attempt lock and sets `refund_requested_at` before contacting Paymob.
Only verified callback processing clears the marker.

## ADR-0019 — Refund capability is a DocType permission

The custom `refund` permission governs the API and Desk surface; code does not hardcode a role.

## ADR-0020 — Payer links are signed app redirects

Payment Request email links are signed routes that create or reuse an eligible checkout attempt.
Browser input never supplies payment facts.

## ADR-0021 — Notifications are native seeded records

Merchants can manage notification recipients, content, and enablement in Desk without code changes.

## ADR-0024 — Payment-link email is decided at validation

The app sets its signed payment URL at `validate`, before ERPNext's own submit-time email behavior.

## ADR-0029 — Immediate payment only

Every enabled Paymob Integration ID must be configured for immediate/standalone payment. A verified
`Success` settles `Pending → Paid` once. Retired signed flags are stored as `Unsupported`, audited
for review, and never mutate state or the ledger. Refund is the only outbound money movement.

## ADR-0030 — Payer links serialize checkout reuse

Signed payer-link checkout takes Frappe's site-scoped file lock for the Payment Request while it
reloads, reuses a ready attempt, or creates and persists one intention. Desk checkout deliberately
keeps its explicit new-attempt behavior.

## ADR-0031 — Payment-link email only ever addresses the customer

`prepare_payment_email` resolves a recipient itself (the reference doc's `contact_email`, else the
`Customer`'s `email_id`) instead of trusting `Payment Request.email_to`. ERPNext's own fallback for
that field is the reference document's `owner`, which is whoever created the record, not the payer —
mailing a Paymob checkout link to an internal user is worse than mailing no one. When no customer
email can be resolved, the email is muted rather than sent to the wrong address.

## ADR-0032 — A full refund posts from the signed parent re-send

Supersedes ADR-0017. A parent re-send (`has_parent_transaction = 0`) whose signed `amount_cents`
equals Paymob's reported cumulative `refunded_amount_cents`, with `is_refunded` set (both signed
fields) and nothing yet posted on the attempt, is treated as a full refund and posts from the signed
`amount_cents` — the same shared refund path a signed child transaction uses. Evidence: live
transactions `510236778` (EGP 499.00) and `510198387` (EGP 249.00) on `capital`, each a single
parent re-send with no child ever received.

`refunded_amount_cents` is still not HMAC-signed (Paymob signs `amount_cents, is_refunded`, and 18
other fields — see `hmac_verify.py:38-59` — but not this one), so it never supplies the posted
amount; it only selects whether this branch runs. Any other shape — a partial refund, or a re-send
after something has already been posted — still cannot prove its delta and is held for a human
(`_hold_parent_refund`), unchanged. Automatic partial refunds are out of scope: the general fix is an
authenticated Transaction Inquiry read, which belongs to the Phase 10 reconciliation poller.
