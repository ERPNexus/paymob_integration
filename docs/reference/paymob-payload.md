# Paymob transaction payload — full field catalogue

The complete field set Paymob returns for one transaction, captured from a **real Transaction
Inquiry** against the live `capital` sandbox on 2026-08-08 (`POST
/api/ecommerce/orders/transaction_inquiry`, `merchant_order_id = ACC-PRQ-2026-00028-1`). This is
not written from the docs — it is what the wire actually carried.

Why this file exists: `paymob.transactions.redact` stores an **allowlist** of the payload, so the
`raw_payload` on a Paymob Transaction is much smaller than what Paymob sent. That is deliberate
(rules/stored-payment-data.md forbids a second copy of customer identity or card data), but it
means the payload on a stored row is not a reference for what is *available*. This file is. Check
it before adding a field, a refund rule, or a reconciliation check — the data may already be on
the wire.

## What the columns mean

- **Signed** — the field is in `hmac_verify.PROCESSED_CALLBACK_FIELDS`, so its value is covered by
  the HMAC-SHA512 digest and can be trusted to move money. Everything else in a webhook is
  authentic-by-association only: an attacker cannot forge the message, but the unsigned fields are
  not individually protected against a tampered replay.
- **Stored** — currently kept in `raw_payload` by `transactions.redact`.
- Example values for customer identity, merchant identity, and card data are shown as
  `(redacted)`; the *path* is documented, the value never is.

## Three facts this capture settled

1. **Paymob does create a child refund transaction.** This capture *is* one: `id 511470147`,
   `has_parent_transaction: true`, `parent_transaction: 511436444`, `is_refund: true`,
   `amount_cents: 64950` — the refund delta, in a signed field. ADR-0017's premise was never
   wrong; the child simply never arrives by **webhook**. Only the parent re-send does. Transaction
   Inquiry returns the child.
2. **The gateway's own refund ledger is in the payload**, under `data.migs_order`:
   `totalCapturedAmount`, `totalRefundedAmount`, and `status: REFUNDED`. None of it is stored today.
3. **`refunded_amount_cents` was not in the stored allowlist** even though the refund decision
   turns on it — the number is in its own DocType column but was invisible in the evidence blob.

## Field catalogue

| Path | Type | Trust / storage | Example |
|---|---|---|---|
| `id` | int | signed + stored | 511470147 |
| `pending` | bool | signed + stored | False |
| `amount_cents` | int | signed + stored | 64950 |
| `success` | bool | signed + stored | True |
| `is_auth` | bool | signed + stored | False |
| `is_capture` | bool | signed + stored | False |
| `is_standalone_payment` | bool | signed + stored | False |
| `is_voided` | bool | signed + stored | False |
| `is_refunded` | bool | signed + stored | False |
| `is_3d_secure` | bool | signed + stored | False |
| `integration_id` | int | signed + stored | 5782913 |
| `profile_id` | int | — | 1200379 |
| `has_parent_transaction` | bool | signed + stored | True |
| `order` | object(29) | — |  |
| `order.id` | int | signed + stored | 583051381 |
| `order.created_at` | str | — | 2026-08-08T12:23:50.313691 |
| `order.delivery_needed` | bool | — | False |
| `order.merchant` | object(10) | — |  |
| `order.merchant.id` | int | — | (redacted) |
| `order.merchant.created_at` | str | — | (redacted) |
| `order.merchant.phones` | array[1] | — |  |
| `order.merchant.company_emails` | NoneType | — | (redacted) |
| `order.merchant.company_name` | str | — | (redacted) |
| `order.merchant.state` | str | — | (redacted) |
| `order.merchant.country` | str | — | (redacted) |
| `order.merchant.city` | str | — | (redacted) |
| `order.merchant.postal_code` | str | — | (redacted) |
| `order.merchant.street` | str | — | (redacted) |
| `order.collector` | NoneType | — | None |
| `order.amount_cents` | int | — | 129900 |
| `order.shipping_data` | object(17) | — |  |
| `order.shipping_data.id` | int | — | (redacted) |
| `order.shipping_data.first_name` | str | — | (redacted) |
| `order.shipping_data.last_name` | str | — | (redacted) |
| `order.shipping_data.street` | str | — | (redacted) |
| `order.shipping_data.building` | str | — | (redacted) |
| `order.shipping_data.floor` | str | — | (redacted) |
| `order.shipping_data.apartment` | str | — | (redacted) |
| `order.shipping_data.city` | str | — | (redacted) |
| `order.shipping_data.state` | str | — | (redacted) |
| `order.shipping_data.country` | str | — | (redacted) |
| `order.shipping_data.email` | str | — | (redacted) |
| `order.shipping_data.phone_number` | str | — | (redacted) |
| `order.shipping_data.postal_code` | str | — | (redacted) |
| `order.shipping_data.extra_description` | str | — | (redacted) |
| `order.shipping_data.shipping_method` | str | — | (redacted) |
| `order.shipping_data.order_id` | int | — | (redacted) |
| `order.shipping_data.order` | int | — | (redacted) |
| `order.currency` | str | — | EGP |
| `order.is_payment_locked` | bool | — | False |
| `order.is_return` | bool | — | False |
| `order.is_cancel` | bool | — | False |
| `order.is_returned` | bool | — | False |
| `order.is_canceled` | bool | — | False |
| `order.merchant_order_id` | str | stored | (redacted) |
| `order.wallet_notification` | NoneType | — | None |
| `order.paid_amount_cents` | int | — | 129900 |
| `order.notify_user_with_email` | bool | — | False |
| `order.items` | array[1] | — |  |
| `order.items[].name` | str | — | ACC-SINV-2026-00025 |
| `order.items[].description` | str | — | Payment Request for ACC-SINV-2026-00025 |
| `order.items[].amount_cents` | int | — | 129900 |
| `order.items[].quantity` | int | — | 1 |
| `order.order_url` | str | — | NA |
| `order.commission_fees` | int | — | 0 |
| `order.delivery_fees_cents` | int | — | 0 |
| `order.delivery_vat_cents` | int | — | 0 |
| `order.payment_method` | str | — | tbc |
| `order.merchant_staff_tag` | NoneType | — | (redacted) |
| `order.api_source` | str | — | OTHER |
| `order.data` | object(3) | — |  |
| `order.data.send_email` | bool | — | True |
| `order.data.notification_url` | str | — | (redacted) |
| `order.data.send_email_trx_id` | int | — | 511436444 |
| `order.payment_status` | str | — | PAID |
| `order.terminal_version` | NoneType | — | None |
| `order.payme_details` | NoneType | — | None |
| `created_at` | str | signed + stored | 2026-08-08T13:40:42.358874 |
| `transaction_processed_callback_responses` | array[0] | — |  |
| `currency` | str | signed + stored | EGP |
| `source_data` | object(4) | — |  |
| `source_data.pan` | str | signed + stored | (redacted) |
| `source_data.type` | str | signed + stored | card |
| `source_data.tenure` | NoneType | — | None |
| `source_data.sub_type` | str | signed + stored | MasterCard |
| `api_source` | str | — | OTHER |
| `terminal_id` | NoneType | — | None |
| `merchant_commission` | int | — | 0 |
| `accept_fees` | int | — | 0 |
| `installment` | NoneType | — | None |
| `discount_details` | array[0] | — |  |
| `amount_cents_int` | int | — | 64950 |
| `is_void` | bool | — | False |
| `is_refund` | bool | — | True |
| `data` | object(27) | — |  |
| `data.klass` | str | — | MigsPayment |
| `data.amount` | float | — | 64950.0 |
| `data.acs_eci` | str | — | 02 |
| `data.message` | str | — | Approved |
| `data.batch_no` | int | — | 20260808 |
| `data.card_num` | str | — | (redacted) |
| `data.currency` | str | — | EGP |
| `data.merchant` | str | — | (redacted) |
| `data.card_type` | str | — | MASTERCARD |
| `data.created_at` | str | — | 2026-08-08T10:40:43.765521 |
| `data.migs_order` | object(14) | — |  |
| `data.migs_order.id` | str | — | 583051381 |
| `data.migs_order.amount` | float | — | 1299.0 |
| `data.migs_order.status` | str | — | REFUNDED |
| `data.migs_order.currency` | str | — | EGP |
| `data.migs_order.reference` | str | — | _511436444_583 |
| `data.migs_order.chargeback` | object(2) | — |  |
| `data.migs_order.chargeback.amount` | int | — | 0 |
| `data.migs_order.chargeback.currency` | str | — | EGP |
| `data.migs_order.creationTime` | str | — | 2026-08-08T09:24:50.644Z |
| `data.migs_order.merchantAmount` | float | — | 1299.0 |
| `data.migs_order.lastUpdatedTime` | str | — | 2026-08-08T10:40:43.584Z |
| `data.migs_order.merchantCurrency` | str | — | EGP |
| `data.migs_order.totalCapturedAmount` | float | — | 1299.0 |
| `data.migs_order.totalRefundedAmount` | float | — | 1299.0 |
| `data.migs_order.merchantCategoryCode` | str | — | 7299 |
| `data.migs_order.totalAuthorizedAmount` | float | — | 1299.0 |
| `data.order_info` | str | — | 583051381 |
| `data.receipt_no` | str | — | (redacted) |
| `data.migs_result` | str | — | SUCCESS |
| `data.secure_hash` | str | — | (redacted) |
| `data.authorize_id` | str | — | (redacted) |
| `data.transaction_no` | str | — | (redacted) |
| `data.avs_result_code` | str | — |  |
| `data.captured_amount` | float | — | 1299.0 |
| `data.refunded_amount` | float | — | 1299.0 |
| `data.merchant_txn_ref` | str | — | (redacted) |
| `data.migs_transaction` | object(11) | — |  |
| `data.migs_transaction.id` | str | — | 511470147 |
| `data.migs_transaction.stan` | str | — | (redacted) |
| `data.migs_transaction.type` | str | — | REFUND |
| `data.migs_transaction.amount` | float | — | 649.5 |
| `data.migs_transaction.source` | str | — | INTERNET |
| `data.migs_transaction.receipt` | str | — | (redacted) |
| `data.migs_transaction.acquirer` | object(7) | — |  |
| `data.migs_transaction.acquirer.id` | str | — | (redacted) |
| `data.migs_transaction.acquirer.date` | str | — | (redacted) |
| `data.migs_transaction.acquirer.batch` | int | — | (redacted) |
| `data.migs_transaction.acquirer.timeZone` | str | — | (redacted) |
| `data.migs_transaction.acquirer.merchantId` | str | — | (redacted) |
| `data.migs_transaction.acquirer.transactionId` | str | — | (redacted) |
| `data.migs_transaction.acquirer.settlementDate` | str | — | (redacted) |
| `data.migs_transaction.currency` | str | — | EGP |
| `data.migs_transaction.terminal` | str | — | BMNF0495 |
| `data.migs_transaction.reference` | str | — | _511470147 |
| `data.migs_transaction.authorizationCode` | str | — | (redacted) |
| `data.acq_response_code` | str | — | 00 |
| `data.authorised_amount` | float | — | 1299.0 |
| `data.txn_response_code` | str | — | APPROVED |
| `data.avs_acq_response_code` | str | — | 00 |
| `data.gateway_integration_pk` | int | — | 5782913 |
| `is_hidden` | bool | — | False |
| `payment_key_claims` | NoneType | — | None |
| `error_occured` | bool | signed + stored | False |
| `is_live` | bool | — | False |
| `other_endpoint_reference` | NoneType | — | None |
| `refunded_amount_cents` | int | — | 0 |
| `refunded_amount_cents_int` | int | — | 0 |
| `source_id` | int | — | -1 |
| `is_captured` | bool | — | False |
| `captured_amount` | int | — | 0 |
| `captured_amount_int` | int | — | 0 |
| `settlement_amount_cents_int` | int | — | 0 |
| `merchant_staff_tag` | NoneType | — | None |
| `accept_fees_cents_int` | int | — | 0 |
| `vat_cents_int` | int | — | 0 |
| `vat_cents_float` | NoneType | — | None |
| `updated_at` | str | — | 2026-08-08T13:40:43.772950 |
| `is_settled` | bool | — | False |
| `bill_balanced` | bool | — | False |
| `is_bill` | bool | — | False |
| `owner` | int | signed + stored | 2403671 |
| `parent_transaction` | int | — | 511436444 |
| `unique_ref` | str | — | (redacted) |
