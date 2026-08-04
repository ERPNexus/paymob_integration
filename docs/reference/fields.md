# Fields

## Paymob Payment Attempt

An attempt owns lifecycle state independently from its Payment Request. Important immutable checkout
facts are `special_reference`, `paymob_order_id`, expected integer `amount_cents`, `currency`,
country, and mode. `state` is one of `Pending`, `Paid`, `Partially Refunded`, `Refunded`, `Failed`,
or `Expired`.

`refund_requested_at` is an in-progress marker set under the refund row lock and cleared only after
a verified refund is processed. `refunded_amount_cents` is the sum of signed child refund deltas.
`needs_human_attention` flags review without changing lifecycle state.

## Paymob Transaction

This append-only log stores one verified or recovered gateway event. `event_key` prevents duplicate
delivery; `event_kind` is `Success`, `Decline`, `Pending`, `Refund`, or `Unsupported`.
`raw_payload` is redacted before storage. Paymob's `is_auth`, `is_capture`, and `is_voided` values
remain there only because the HMAC contract signs them; they are not active fields or workflows.

## Paymob Audit Entry

Audit entries are submitted and immutable. They cover reviewable anomalies and accountability
events, including `Amount Mismatch`, `Duplicate Payment`, `Refund Requested`, and `Unsupported
Paymob Event`. A resolution is a new entry linked through `supersedes`; no entry is edited or
deleted.

## Paymob Integration ID

Each enabled row supplies an immediate-payment Paymob integration ID for a country, currency, and
mode. It has no deferred-settlement field: the app supports immediate payments and refunds only.

## Active configuration and operational contracts

### Functional

Merchants configure credentials, defaults, integration IDs, and payment-account mappings in
`Paymob Settings`. They can test the connection, while authorized Desk users can manually process
an unprocessed transaction.

### Technical

`Paymob Settings` stores the site enable switch, mode, credential rows, integration rows, API
defaults, and status-email preferences. `Paymob Settings.test_connection` validates credentials
without creating payment data. `Paymob Transaction.process` invokes the same idempotent processor
used by webhook jobs and requires read permission on the append-only log.
