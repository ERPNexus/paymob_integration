# Rule: Stored Payment Data

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (blocking at review)

## Why this rule exists

Paymob's hosted checkout collects card details on Paymob's own pages. Card data never reaches
this app, and that is not an accident — it is the reason the merchant stays outside most of the
PCI DSS burden.

The moment this app stores a full card number, that changes. The merchant's whole ERPNext site
becomes a system that holds cardholder data, with the audits, scanning, and liability that
follow. One well-meaning field, added to "help support identify the card", is enough to do it.

## The requirement

### Never store, never accept, never log

- The full card number (PAN).
- CVV / CVC — this may never be stored by anyone, under any condition, even encrypted.
- The magnetic stripe or chip data.
- The card PIN.

This applies to database fields, log lines, audit records, error messages, and test fixtures.
If one of these values ever appears in a request to this app, that is a design defect: it means
something bypassed the hosted checkout.

### What may be stored

Only what Paymob returns for display and reconciliation:

- Last four digits, and the card brand.
- The Paymob transaction ID, order ID, and intention identifiers.
- Amounts, currency, state, and timestamps.
- The card token, if saved-card payments are implemented later — a token is a reference held by
  Paymob, not card data. That feature needs its own decision entry before it is built.

### Personal data

- Store the minimum needed to reconcile a payment and contact the customer about it.
- The billing details sent to Paymob come from the existing ERPNext customer record. Do not
  create a second copy of customer personal data inside this app.

## Definition of Done

- [ ] No new field can hold a full card number, CVV, or raw card data.
- [ ] No log line, audit record, error message, or test fixture contains card data.
- [ ] Any card reference stored is a token or a masked last-four, and is documented in
      `docs/reference/fields.md`.
- [ ] No new copy of customer personal data was introduced.

## What this rule is NOT

- Not a full PCI DSS compliance programme. It is the one boundary that keeps the merchant's
  scope small. Formal compliance is the merchant's responsibility.
- Not about credentials — those are in [`secrets.md`](secrets.md).
