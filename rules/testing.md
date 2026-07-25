# Rule: Testing

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (blocking at review)

## Why this rule exists

Payment bugs are discovered by customers, not by developers. The failure modes that matter —
a replayed webhook, a lost response, a forged signature, two clicks in one second — never
happen while you are watching. They happen at 2am, once in a thousand payments.

A test is the only way to see those paths on purpose. It is also the only way to check that
generated code still behaves correctly after the next AI edits it.

## The requirement

### Never call Paymob in a test

Tests use recorded or hand-written Paymob responses. No test may make a network call. A test
suite that depends on Paymob being up, or on test credentials being valid, is a test suite that
will be disabled the first time it goes red for the wrong reason.

### Every money path ships with these tests

**Unit tests** (single function, no site interaction where possible):

- Signature verification: valid signature passes; wrong signature rejected; tampered field
  rejected; missing `hmac` rejected.
- Amount comparison: exact match passes; over-payment and under-payment are rejected as
  mismatches; the cents conversion is exact for values like `275.55`.
- State transitions: each legal transition allowed, each illegal one refused.

**Integration tests** (real documents on a test site):

- Full success flow: intention → verified webhook → Payment Entry created, submitted, and
  allocated to the Sales Invoice; invoice becomes Paid.
- Duplicate webhook delivery: the same message twice produces exactly **one** Payment Entry and
  returns HTTP 200 both times.
- Two genuine payments for one Payment Request: one Payment Entry, one audit record.
- Amount mismatch: audit record created, no Payment Entry, invoice untouched.
- Failed payment: status updated, zero GL rows, Sales Invoice untouched.
- Refund: opposite Payment Entry created only on the verified refund webhook.
- Permission: a user without permission calling a money-moving whitelisted method is refused.
- Lost webhook: the poller finds the payment through Transaction Inquiry and posts it through
  the same shared function.

### Assertions must check the ledger

Asserting that a function returned without an error proves nothing. Money tests assert on the
resulting rows: how many Payment Entries exist, their amounts, their allocations, and the GL
effect. "No ledger row was created" is asserted by counting, not assumed.

## Definition of Done

- [ ] New money path has unit tests for its validation and state rules.
- [ ] New money path has integration tests for success, duplicate, mismatch, and failure.
- [ ] Every test that involves a money path asserts on Payment Entry count and allocation.
- [ ] No test performs a network call.
- [ ] `bench --site <site> run-tests --app paymob_integration` passes.

## What this rule is NOT

- Not a coverage percentage target. A high number over trivial code is not evidence of safety.
  The named scenarios above are the evidence.
- Not a demand for UI tests. Desk behaviour is checked by hand until a repeated regression
  justifies automating it.
