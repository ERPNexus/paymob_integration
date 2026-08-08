# Endpoints, Settings & Errors

## Public application endpoints

| Endpoint | Purpose | Ledger authority |
|---|---|---|
| `get_enabled_status` | Returns the site-wide enabled state to Desk. | No |
| `start_checkout` | Creates a new Desk checkout and starts hosted checkout. | No |
| `request_refund` | Requests one full or partial refund under a row lock and `refund` permission. | No |
| `processed_callback` | Verifies, stores, and queues signed Paymob transaction facts. | Yes, through the processor only |

`processed_callback` is the sole `allow_guest=True` endpoint. It verifies HMAC-SHA512 with
`hmac.compare_digest` before any payload-directed database access, then persists before returning
HTTP 200. Duplicate event keys also return HTTP 200 without a second write. Internal storage errors
return non-2xx so Paymob can retry.

The signed `/paymob-pay` route reuses one ready, unexpired checkout per Payment Request. Its
site-scoped lock covers the active-attempt lookup through intention creation and identifier
persistence. Callback attribution requires both the merchant reference and signed Paymob order ID
to match the stored attempt.

## Refund request

`request_refund` requires the custom `refund` permission on a `Paid` or `Partially Refunded`
attempt. It locks the attempt, rejects a second in-progress request, derives the maximum from the
verified `Success` transaction, records `Refund Requested`, and calls
`POST /api/acceptance/void_refund/refund` once. A response never posts a Payment Entry; only the
later signed refund callback can do that. Outbound writes are never retried automatically.

## Settings

`Paymob Settings.is_enabled` is a server-side feature boundary for checkout, refund, callbacks,
and reconciliation. `resolve_integrations(country, currency)` returns every enabled integration ID
for the selected country, currency, and mode. Each enabled Paymob dashboard integration must be
configured for immediate/standalone payment.

## Active settings and failure paths

`Paymob Settings` also owns encrypted API credentials, public keys, base URLs, checkout expiration,
payment-account mappings, and notification toggles. A fixed 20-minute window
(`api.REFUND_CONFIRMATION_MINUTES`) bounds how long `request_refund`'s in-progress marker blocks a
second request: past that window the lock self-releases instead of waiting forever for a callback
Paymob may never send. `test_connection` is a
read-only administrator action that validates credentials and reports a translated failure; it
does not create a transaction or Payment Entry. The Desk `Paymob Transaction.process` action is a
manual rescue for a stored row with `processed = 0` and routes through the same processor as the
webhook worker. Missing credentials, disabled Paymob, invalid signatures, gateway failures, and
amount/currency mismatches fail closed: no ledger row is created and the attempt remains available
for retry or human review according to its audit entry.

## Unsupported signed flags

Callbacks carrying `is_auth`, `is_capture`, or `is_voided` are accepted only as signed evidence.
They become `Unsupported`, are stored with redaction, and create review work; they do not call an
outbound endpoint, transition a Payment Attempt, or mutate the ledger.
