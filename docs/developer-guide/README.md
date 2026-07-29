# Developer Guide

**Audience:** the developer installing, configuring, extending, or integrating the app.

How to *build against* and *operate* the app technically. Written as features ship (per
[../../rules/documentation.md](../../rules/documentation.md)). Link into
[../reference/](../reference/) for exact states, fields, decisions, and endpoint contracts.

## Planned topics (filled as slices land)

- Install & site setup (`bench get-app`, `install-app`, `migrate`).
- Configuring credentials and integration IDs securely.
- The payment flow end to end (see [../architecture.md](../architecture.md)).
- Webhook/callback contracts and HMAC verification (see [endpoints](../reference/endpoints.md)).
- Extension points (hooks) and how to test payment flows.

## Payer links and notifications

`Payment Request.before_submit` sets `payment_url` only for an enabled, configured Paymob inward
request. `/paymob-pay` verifies Frappe's signed query before loading that request and uses
`api._checkout(..., reuse_pending=True)` to prevent a refresh from creating another intention.
`notifications.seed()` is called after install and by the post-model-sync patch; it creates missing
non-standard Notification records and never updates an existing one. A one-time corrective patch refreshes
the seven shipped templates, then later Desk edits in **Notifications** are preserved. Templates brand
customer messages with the linked Payment Request Company; Frappe sends them through the site's configured
**Email Account**, which controls the From address and display name. See [endpoints](../reference/endpoints.md)
and [decisions](../reference/decisions.md) for the contract.
