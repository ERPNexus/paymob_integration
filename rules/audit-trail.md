# Rule: Audit Trail

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (blocking at review)

## Why this rule exists

Two situations need a record that outlives a log file.

The first is money that arrived but was not posted: an authentic callback whose amount does not
match, or a second genuine payment for one order. [`payments.md`](payments.md) forbids posting
these automatically. If nothing durable records them, the money is simply lost.

The second is an accounting question months later: who refunded this, when, and on what
evidence? Logs are rotated. An accountant's question is not.

## The requirement

### Record every money-affecting event

An audit record is created for each of these, and it is a document in the database, not a log
line:

- Authentic callback with an amount mismatch (nothing posted, human review needed).
- A second genuine payment for a Payment Request already paid (refund needed).
- Refund, void, or capture requested — who requested it and with what parameters.
- A payment state changed by the poller rather than by a callback.
- A verification failure that was not an obvious scan (repeated failures on a real reference).

### What each record holds

- The Payment Request, and the Paymob transaction ID where one exists.
- What happened, in a form a non-developer can read.
- The amounts involved: expected and received, in cents.
- Who caused it — the user, or the system job that ran.
- When, in UTC.
- Whether a human still needs to act, and a place to record that they did.

### Immutable

Audit records are never edited or deleted after creation. A correction is a new record that
refers to the earlier one. If a record is wrong, that fact is itself information worth keeping.

### Visible

A record that needs human action must be findable without SQL — a list view a merchant or
accountant can open, filtered to "needs action". A record nobody can see is not a control.

## Definition of Done

- [ ] Every new money-affecting event creates an audit record.
- [ ] Records that need human action are visible in a list view and marked as pending.
- [ ] No code path edits or deletes an existing audit record.
- [ ] Every audit record names the payment, the amounts, the actor, and the time.

## What this rule is NOT

- Not a replacement for Frappe's built-in document versions and comments, which continue to
  work normally.
- Not a general activity log. Only money-affecting events belong here; everything else is
  [`logging.md`](logging.md).
