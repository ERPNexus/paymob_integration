# Rule: Accuracy Over Assumption

**Status:** Active · **Since:** 2026-08-06 · **Enforcement:** Convention (blocking at review)

## Why this rule exists

This session lost real time chasing a refund bug that turned out to be a wrong assumption about
Paymob's callback behavior — built and shipped without checking Paymob's actual docs first. In a
payment integration, a guessed endpoint, a guessed payload shape, or a guessed number of
callbacks doesn't fail loudly. It fails by posting the wrong thing, or silently not posting at
all, and the money is already moved on Paymob's side before anyone notices.

## The requirement

Before planning, implementing, or debugging anything that depends on a Paymob API contract
(endpoint URL, request/response shape, headers, HMAC fields, callback count and ordering, status
codes, idempotency behavior, error formats) — confirm it against a primary source:

- Paymob's official docs, or
- Paymob's official Postman collection, or
- an actual logged request/response captured from this app's own traffic.

Internal memory, prior training data, or "this is how most payment gateways do it" is not a
source. If none of the primary sources answer the question, say so explicitly instead of
proceeding on a best guess:

> "I don't have a confirmed source for [X]. I can [ask you to check Paymob's docs / point me to
> the doc section / proceed with an assumption you approve first] — which do you want?"

This applies to plans and implementations alike. A plan that says "Paymob sends one callback per
refund" needs that claim checked, not asserted.

## Definition of Done

- [ ] Every claim about a Paymob endpoint, payload, or behavior used in the change is traceable
      to a doc link, Postman collection entry, or a logged request/response — cited in the PR or
      commit body.
- [ ] Anywhere the actual behavior couldn't be confirmed, that gap was surfaced to the user
      before code was written, not discovered after.
- [ ] No code path silently assumes callback count, ordering, or field presence that isn't
      confirmed by a primary source.

## What this rule is NOT

- Not a ban on reasonable defaults for things Paymob's docs don't specify (e.g., internal retry
  backoff) — those are our own design choices, not claims about Paymob's behavior.
- Not a requirement to re-verify settled, already-cited facts on every touch of the same code.
