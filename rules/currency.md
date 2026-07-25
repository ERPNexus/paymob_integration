# Rule: Currency

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (Definition of Done)

## Why this rule exists

An amount without a currency is not money — it is a number.

Paymob operates in Egypt, Saudi Arabia, the UAE, Oman, and Pakistan, and integration IDs are
bound to a currency. So a Paymob account can genuinely return 500000 cents of SAR against an
invoice raised in EGP. If the code compares only the number, that payment matches perfectly and
posts a ledger entry roughly thirteen times too small.

This is cheap to prevent now and expensive to fix after the ledger is wrong.

## The requirement

- Every stored amount is stored with its currency code. No amount field exists on its own.
- The currency comparison is part of the amount check in [`payments.md`](payments.md): a
  callback matches only if **both** the integer cents and the currency code match what was
  expected.
- A currency mismatch is treated exactly like an amount mismatch: audit record, nothing posted,
  human review.
- Never assume EGP as a default anywhere — not in a function argument, not in a settings
  default, not in a test fixture that other tests copy.
- Cents are a currency-specific idea. The conversion between the displayed amount and the minor
  unit follows the currency, and is done once at the intention boundary.
- Payment Entries post in the currency actually received, and any conversion to the company
  currency uses ERPNext's exchange rate handling — never a rate calculated in this app.

## Definition of Done

- [ ] Every new amount field has a currency alongside it.
- [ ] The amount check compares currency as well as value.
- [ ] No hardcoded `"EGP"` outside settings defaults and clearly labelled test data.
- [ ] No exchange rate is computed inside this app.

## What this rule is NOT

- Not multi-currency support as a feature. This rule only makes sure a mismatch is *caught*.
  Actually selling in several currencies is a separate slice with its own decision entry.
