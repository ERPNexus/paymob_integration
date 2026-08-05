# Developer Guide

**Audience:** the developer installing, configuring, extending, or integrating the app.

See the [architecture](../architecture.md) for the end-to-end flow and
[reference documentation](../reference/) for exact states, fields, decisions, and endpoint contracts.

## Payer links and notifications

`Payment Request.before_submit` sets `payment_url` only for an enabled, configured Paymob inward
request. `/paymob-pay` verifies Frappe's signed query before loading that request and uses
`api._checkout(..., reuse_pending=True)`. A Payment-Request-scoped site lock makes simultaneous
opens recheck and reuse the same ready, unexpired checkout rather than create competing intentions.
Webhook attribution additionally requires both `merchant_order_id` and signed `order.id` to match
the frozen attempt identifiers.
`notifications.seed()` is called after install and by the post-model-sync patch; it creates missing
non-standard Notification records and never updates an existing one. A one-time corrective patch refreshes
the seven shipped templates, then later Desk edits in **Notifications** are preserved. Templates brand
customer messages with the linked Payment Request Company; Frappe sends them through the site's configured
**Email Account**, which controls the From address and display name. See [endpoints](../reference/endpoints.md)
and [decisions](../reference/decisions.md) for the contract.

## Local checks

Use Frappe/ERPNext `version-16` with Python `>=3.14,<3.15`. The app has no live Paymob calls in
automated tests; HTTP calls are mocked and credentials are fake fixtures only.

```bash
pre-commit install
pre-commit run --all-files
bench --site <clean-site> migrate
bench --site <clean-site> run-tests --app paymob_integration
```

Keep integration tests on `NoCommitIntegrationTestCase`, assert Payment Entry count and allocation,
and never call `frappe.db.commit()` in tests. Review money-moving changes against
[`rules/payments.md`](../../rules/payments.md) and [`rules/implementation-gate.md`](../../rules/implementation-gate.md).

## Sandbox acceptance

Run the [sandbox smoke-test checklist](sandbox-smoke-test.md). Record only non-sensitive evidence;
do not attach credentials, HMAC secrets, card data, or raw webhook payloads.
