# References

All sources accessed **2026-07-15**. Paymob's docs site (developers.paymob.com, Theneo-hosted) blocks plain HTTP fetchers with 403; pages were retrieved through a rendering fetcher. Most pages also expose a raw-markdown variant by appending `.md` to the URL — useful for future re-verification.

## Paymob official documentation

| Topic | URL |
|---|---|
| Developer portal root | https://developers.paymob.com/ |
| Create Intention API (endpoint, auth, body, response, common errors, regional base URLs) | https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention |
| Checkout Experiences overview (Unified Checkout vs Pixel) | https://developers.paymob.com/paymob-docs/developers/checkout-experiences |
| Unified Checkout redirection (URL format: `/unifiedcheckout/?publicKey=&clientSecret=`) | https://developers.paymob.com/paymob-docs/developers/checkout-experiences/unified-checkout-redirection |
| Webhook (Callbacks) & HMAC overview — "callback only if the transaction succeeds or is declined" | https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac |
| Transaction callbacks (processed vs response, key fields, sample payload + sample redirect URL, ngrok/testing note, HMAC caution) | https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/transaction-callbacks |
| HMAC overview (what/why) | https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/hmac |
| HMAC Transaction Callback (exact 20-key list, POST-vs-GET name mapping, sample concatenated string, SHA-512, hex compare) | https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/hmac/hmac-transaction-callback |
| HMAC Card Token Callback (8-key list for TOKEN callbacks) | https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/hmac/hmac-for-card-tokens |
| Refund API (`POST /api/acceptance/void_refund/refund`, secret-key auth, partial-refund error, parent-transaction note) | https://developers.paymob.com/paymob-docs/developers/manage-payment-apis |
| Void (concept: before settlement, card-only) | https://developers.paymob.com/paymob-docs/developers/manage-payment-apis/void.md |
| Capture (concept: finalizes auth, full/partial, before auth expiry) | https://developers.paymob.com/paymob-docs/developers/manage-payment-apis/capture.md |
| Transaction Inquiry — by transaction ID (`GET /api/acceptance/transactions/{id}`, Bearer auth-token) | https://developers.paymob.com/paymob-docs/developers/transaction-inquiry-apis |
| Getting Integration Credentials (secret/public/API key retrieval; API key same across modes; callback URLs per integration ID) | https://developers.paymob.com/paymob-docs/getting-started-with-paymob/getting-integration-credentials |
| Test Credentials (test cards, test wallet number/MPin/OTP) | https://developers.paymob.com/paymob-docs/need-help/faq/test-credentials.md |
| Getting-started overview (payment methods incl. 3DS mention, sandbox-vs-production, regional base URLs EGY/OMN/KSA/UAE, "same base URL, mode controlled by keys") | rendered at multiple sidebar routes, e.g. https://developers.paymob.com/paymob-docs/developers/checkout-experiences/692e3ef227393304f3d695fd/69554d7c885397a8b1dac6ed/69554eceb00398adb7e25626 |

## Paymob official code artifacts

| Topic | URL |
|---|---|
| Postman collections repo (verified: Refund/Void/Capture endpoints + `Token {{Secret_Key}}` header; Inquiry endpoints; `POST /api/auth/tokens {"api_key"}`) | https://github.com/PaymobAccept/API-Postman-Collections |
| paymob-js (flash/embedded checkout handbook) | https://github.com/PaymobAccept/paymob-js |

## Dead/unreachable during research (noted so nobody re-chases them)

- https://docs.paymob.pk — DNS does not resolve as of 2026-07-15 (Pakistan docs mirror). Pakistan base URL therefore NEEDS VERIFICATION.
- https://docs.paymob.com/docs/void-transaction — 302-redirects to app.theneo.io legacy portal.
- https://docs.paymob.sa/docs/hmac-calculation — JS-only shell, no content retrievable.

## ERPNext connector cross-check

| Topic | URL |
|---|---|
| Ecosire "Paymob Gateway for ERPNext" (feature list used to cross-check completeness: encrypted-credential Settings doctype, HMAC-verified whitelisted webhook, auto Payment Entry allocation, `Paymob Transaction` audit doctype, hourly/daily reconciliation of stuck intents, refund write-back, role gating, multi-country integration IDs, tokenized recurring, BNPL) | https://ecosire.com/apps/erpnext/erpnext-paymob-gateway |

## ERPNext / Frappe (ledger-mapping side)

| Topic | URL |
|---|---|
| frappe/payments app (Payment Gateway doctype + gateway controller pattern) | https://github.com/frappe/payments |
| Payment Request | https://docs.frappe.io/erpnext/user/manual/en/payment-request |
| Payment Entry | https://docs.frappe.io/erpnext/user/manual/en/payment-entry |
| Payment Reconciliation | https://docs.frappe.io/erpnext/user/manual/en/payment-reconciliation |

## General payment-architecture background (non-Paymob)

| Topic | URL |
|---|---|
| Webhook best practices incl. duplicate-event handling & signature verification (industry reference) | https://docs.stripe.com/webhooks |

## Known unknowns (explicitly not answered by any source above — test empirically)

1. Webhook retry/redelivery policy for the transaction processed callback — **undocumented**.
2. API rate limits (intention creation, inquiry) — **undocumented**.
3. Auth-token (from `/api/auth/tokens`) lifetime — **undocumented** in current pages.
4. HMAC secret: shared or distinct between test/live — **not stated**.
5. GET response-callback order param name: docs text says `order_id`, official sample URL uses `order` — **contradictory, verify with a logged real redirect**.
6. Pakistan region base URL / current status — docs mirror offline.
7. Test-vs-live behavioral parity for callbacks (timing, wallet/BNPL coverage) — **not stated**.
