# Rule: Logging

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (Definition of Done)

## Why this rule exists

When a customer says "I paid and my invoice still shows unpaid", you need to answer one
question fast: how far did this payment get? Was the intention created? Did the customer reach
checkout? Did a webhook arrive? Did it fail verification? Did the amount not match?

You can only answer that if each stage left a line behind, and if all those lines can be found
with one search.

## The requirement

### One key ties everything together

Every log line about a payment includes the **Payment Request name** (for example `PR-00042`).
It is the thread that connects intention, checkout, webhook, poller, and ledger. Where a Paymob
transaction ID exists, include it too.

### Log these stages

| Stage | Log |
|---|---|
| Intention created | Payment Request, Paymob order ID, expected amount in cents |
| Webhook received | Payment Request, transaction ID, whether verification passed |
| Webhook rejected | reason category only (bad signature, unknown reference, duplicate) |
| Amount mismatch | expected cents, received cents, audit record name |
| Payment Entry posted | Payment Request, Payment Entry name, amount |
| Poller action | how many payments checked, which ones changed state |
| Outbound call | endpoint, transaction ID, outcome (never the request body) |

### Never log

- Credentials of any kind — see [`secrets.md`](secrets.md).
- Full card numbers, CVV, or any raw card data — see
  [`stored-payment-data.md`](stored-payment-data.md). Card numbers appear masked or not at all.
- The complete webhook payload. Log the fields listed above, not the whole body.
- Customer phone numbers and email addresses, unless the line genuinely needs them.

### How

- Use `frappe.logger("paymob")` for stage lines and `frappe.log_error` for failures that need a
  human.
- Log lines are English and are not translated — they are for developers.
- Write one line per stage. Debug logging that fires per loop iteration does not get committed.

## Definition of Done

- [ ] Every new payment stage logs one line including the Payment Request name.
- [ ] No credential, card data, or full payload appears in any log line.
- [ ] Failures are logged with enough context to find the payment, and no more.
- [ ] No leftover `print()` or temporary debug logging in the change.

## What this rule is NOT

- Not an audit trail. Logs are for debugging and may be rotated away. Records that must survive
  are in [`audit-trail.md`](audit-trail.md).
- Not a monitoring or alerting design. That is a later decision, recorded in
  `docs/reference/decisions.md` when it is made.
