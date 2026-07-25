# Glossary — Paymob & Payment-Integration Terms

Every term below is defined from a verified source (see `references.md` for full URLs and access dates, all accessed 2026-07-15). Entries marked **NEEDS VERIFICATION** could not be confirmed in official docs and must be tested empirically.

---

## Paymob credentials (four different secrets — do not confuse them)

### Secret Key (`sk_test_...` / `sk_live_...`)
Server-side API credential. Sent as `Authorization: Token sk_...` on the Create Intention, Refund, Void, and Capture APIs. There are **separate test and live secret keys**; the key's mode must match the mode of the integration IDs you use. Never exposed to the browser.
*Source: [Create Intention](https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention), [Getting Integration Credentials](https://developers.paymob.com/paymob-docs/getting-started-with-paymob/getting-integration-credentials).*

### Public Key (`pk_...`)
Client-side, non-secret identifier. Used only in the Unified Checkout URL (`?publicKey=...`) or when initializing the Pixel embedded SDK. Also mode-specific (test/live).
*Source: [Unified Checkout (Redirection)](https://developers.paymob.com/paymob-docs/developers/checkout-experiences/unified-checkout-redirection), [Getting Integration Credentials](https://developers.paymob.com/paymob-docs/getting-started-with-paymob/getting-integration-credentials).*

### API Key
Legacy credential from the dashboard Settings tab. Exchanged for a short-lived **auth token** via `POST /api/auth/tokens` with body `{"api_key": "..."}`. That auth token is then used as a `Bearer` token on the Transaction Inquiry APIs. Unlike the secret/public keys, **the API key is the same for both test and live modes**.
*Source: [Getting Integration Credentials](https://developers.paymob.com/paymob-docs/getting-started-with-paymob/getting-integration-credentials) ("It's the same key for both environments"), [official Postman collection "Transaction Inquiry API"](https://github.com/PaymobAccept/API-Postman-Collections).*
**NEEDS VERIFICATION:** the auth token's exact lifetime (commonly cited as ~1 hour) is not stated in the current docs — test it.

### HMAC Secret
A separate secret from the dashboard used **only to verify callbacks** (webhooks and redirects) sent by Paymob to you. It is never sent in your API requests. If you skip HMAC verification, you cannot tell a genuine Paymob callback from a forged one.
*Source: [HMAC overview](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/hmac).*
**NEEDS VERIFICATION:** whether the HMAC secret differs between test and live modes is not explicitly stated in the docs.

### Integration ID
A numeric ID representing **one payment method configuration** (e.g., "online card in EGP", "mobile wallet") in your dashboard under Developers → Payment Integrations. Each integration ID is either test or live, and its mode **must match the secret key's mode** or the Intention API returns `404 "Integration ID/Name does not exist"`. You pass one or more integration IDs in the intention's `payment_methods` array. Callback URLs (processed + response) are configured **per integration ID**.
*Source: [Create Intention — Common Errors](https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention), [Getting Integration Credentials](https://developers.paymob.com/paymob-docs/getting-started-with-paymob/getting-integration-credentials).*

### Iframe ID (legacy)
ID of a hosted-iframe checkout in the old (pre-Intention) flow. The Intention API response still returns `iframe_id` inside `payment_keys` (may be `null`). New integrations should use Unified Checkout / Pixel, not the legacy iframe.
*Source: [Create Intention response sample](https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention).*

---

## Paymob flow objects

### Intention (Payment Intention)
The object your **backend** creates to start a payment: `POST {base}/v1/intention/` with amount (in cents), currency, `payment_methods` (integration IDs), `items`, `billing_data`, and optional `special_reference`, `extras`, `expiration`, `notification_url`, `redirection_url`. Response includes `id` (`pi_...`), `intention_order_id`, `client_secret`, and `status: "intended"`.
*Source: [Create Intention](https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention).*

### Client Secret (`egy_csk_test_...`)
A unique, intention-specific token returned by Create Intention. It is the bridge between your backend and the checkout UI: you redirect the customer to Unified Checkout with it (or feed it to Pixel). It represents one payment attempt.
*Source: [Checkout Experiences overview](https://developers.paymob.com/paymob-docs/developers/checkout-experiences).*

### Order ID (Paymob order ID)
Paymob-generated ID (`intention_order_id` in the create response, `order.id`/`order` in callbacks). This is the primary correlation key between a Paymob callback and the record on your system.
*Source: [Create Intention — Key values in the response](https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention).*

### Special Reference / `merchant_order_id`
**Your** unique reference (e.g., ERPNext Payment Request name), passed as `special_reference` when creating the intention and echoed back as `merchant_order_id` in the transaction callback. Because it must be unique on Paymob's side, it doubles as an idempotency guard against creating two Paymob orders for the same ERPNext document.
*Source: [Create Intention body parameters](https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention).*

### Unified Checkout
Paymob's hosted, redirect-based payment page: `GET {base}/unifiedcheckout/?publicKey={pk}&clientSecret={cs}`. Card data is entered on Paymob's page, keeping you out of PCI scope. Appearance is customizable from the dashboard.
*Source: [Unified Checkout (Redirection)](https://developers.paymob.com/paymob-docs/developers/checkout-experiences/unified-checkout-redirection).*

### Pixel
Paymob's JavaScript SDK for an **embedded** checkout inside your own page (cards, Apple Pay, Google Pay) using the same intention + client secret. Alternative to redirecting; more integration effort.
*Source: [Checkout Experiences overview](https://developers.paymob.com/paymob-docs/developers/checkout-experiences).*

### Hosted iframe (legacy)
The older embed model where a Paymob iframe (identified by iframe ID + payment key) was placed in your page. Superseded by Unified Checkout/Pixel for new builds; you will still see `api_source: "IFRAME"` in some callback samples.
*Source: [Create Intention response](https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention) (iframe_id field); overview table listing "Hosted checkout" as the current redirect option.*

---

## Callbacks

### Transaction Processed Callback (the webhook)
Server-to-server `POST` of a JSON body `{"type": "TRANSACTION", "obj": {...}}` to your backend endpoint, sent **only when a transaction succeeds or is declined** (also after later actions on the payment such as refund/void/capture). The HMAC arrives as a **query parameter** (`?hmac=...`) on your callback URL. This is the callback you trust (after HMAC verification) to update ledgers. Key fields: `obj.id` (transaction ID), `obj.success`, `obj.pending`, `obj.order.id`, `obj.is_refunded`, `obj.refunded_amount_cents`, `obj.is_voided`, `obj.is_captured`, `obj.captured_amount`, `obj.order.merchant_order_id`.
*Source: [Transaction callbacks](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/transaction-callbacks), [Webhook overview](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac).*

### Transaction Response Callback (the redirect)
Client-side `GET` redirect of the **customer's browser** back to your site after payment, with transaction details as query parameters (including its own `hmac`). Purpose: show the customer a result page. It is *not* a substitute for the webhook — the browser may never arrive (closed tab, dropped connection).
*Source: [Transaction callbacks](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/transaction-callbacks) — comparison table: Processed = POST/JSON/server-side; Response = GET/query-params/client-side.*

### `notification_url` / `redirection_url` (per-intention overrides)
Optional Create Intention fields that override the integration-ID-level callback URLs for that one intention. `notification_url` (processed callback) is documented as supported **only with card integration IDs**; `redirection_url` for card and wallet only.
*Source: [Create Intention body parameters](https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention).*

### Card Token Callback
A `POST` callback of `{"type": "TOKEN", "obj": {...}}` sent when a card is tokenized (saved-card flows). Has its own HMAC key list: `card_subtype, created_at, email, id, masked_pan, merchant_id, order_id, token`.
*Source: [HMAC Card Token Callback](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/hmac/hmac-for-card-tokens).*

### HMAC-SHA512 verification (Paymob's exact recipe)
For transaction callbacks (both processed and response): take these values **in this exact lexicographic key order**, concatenate them into one string, compute HMAC-SHA512 with your HMAC secret, hex-encode lowercase, and compare with the received `hmac`:

```
amount_cents, created_at, currency, error_occured, has_parent_transaction,
id            (obj.id in POST body | id query param in GET),
integration_id, is_3d_secure, is_auth, is_capture, is_refunded,
is_standalone_payment, is_voided,
order.id      (order.id in POST body | order id param in GET — see note),
owner, pending, source_data.pan, source_data.sub_type, source_data.type, success
```

Booleans are concatenated as lowercase `true`/`false` (per the official sample string).
*Source: [HMAC Transaction Callback](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/hmac/hmac-transaction-callback).*
**NEEDS VERIFICATION:** the docs text says the GET param is `order_id`, but the official sample redirect URL uses `order=378804`. Confirm the actual query-param name empirically before relying on it.

---

## Payment operations

### Refund
`POST {base}/api/acceptance/void_refund/refund` with `Authorization: Token <secret_key>` and body `{"transaction_id": ..., "amount_cents": ...}`. Partial refunds are allowed (multiple partials possible); requesting more than the refundable amount returns `400`. A refund is a **new child transaction** (`is_refund: true`, `parent_transaction: <id>`); the parent's subsequent callbacks show `is_refunded: true` and `refunded_amount_cents`.
*Source: [Refund API](https://developers.paymob.com/paymob-docs/developers/manage-payment-apis) + [official Postman collection](https://github.com/PaymobAccept/API-Postman-Collections).*

### Void
`POST {base}/api/acceptance/void_refund/void` with `Authorization: Token <secret_key>` and body `{"transaction_id": ...}`. Cancels a successful payment **before settlement** (typically same business day); card payments only; the customer is never charged, so no separate refund occurs.
*Source: [Void](https://developers.paymob.com/paymob-docs/developers/manage-payment-apis/void.md) + [official Postman collection](https://github.com/PaymobAccept/API-Postman-Collections).*

### Auth / Capture
Two-phase card flow: an **authorization** (`is_auth: true`) reserves funds; **capture** (`POST {base}/api/acceptance/capture`, body `{"transaction_id", "amount_cents"}`) transfers them. Full or partial capture allowed, must happen before the authorization expires; card + auth-type transactions only.
*Source: [Capture](https://developers.paymob.com/paymob-docs/developers/manage-payment-apis/capture.md) + Postman collection.*

### Transaction Inquiry
Pull-based status check — the backbone of reconciliation polling:
- By transaction ID: `GET {base}/api/acceptance/transactions/{transaction_id}` with `Authorization: Bearer <auth_token>` (auth token from API key).
- By order / merchant reference: `POST {base}/api/ecommerce/orders/transaction_inquiry` with `{"order_id": ...}` or `{"merchant_order_id": ...}`.
*Source: [Transaction Inquiry APIs](https://developers.paymob.com/paymob-docs/developers/transaction-inquiry-apis), Postman collection.*

### 3-D Secure (3DS)
Card-network protocol where the issuer authenticates the cardholder (OTP/app challenge) before authorization; shifts fraud liability to the issuer. With Unified Checkout, **Paymob runs the 3DS challenge inside the hosted flow** — you never implement it; you only see the outcome (`is_3d_secure: true`, `data.migs_order.authenticationStatus: "AUTHENTICATION_SUCCESSFUL"`, `acs_eci`) in the callback.
*Source: [Overview — "Standard online card payments with 3D Secure"](https://developers.paymob.com/paymob-docs/developers/checkout-experiences), callback samples in [Transaction callbacks](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/transaction-callbacks).*

---

## Regions, environments, and testing

### Regional base URLs (separate deployments, separate accounts)
- Egypt: `https://accept.paymob.com/`
- Oman: `https://oman.paymob.com/`
- Saudi Arabia: `https://ksa.paymob.com/`
- UAE: `https://uae.paymob.com/`

Each region is a separate platform: a merchant account, its keys, and its integration IDs belong to one region. Currency of the intention must match the integration ID's currency.
*Source: base-URL selector on every API page, e.g. [Create Intention](https://developers.paymob.com/paymob-docs/developers/intention-apis/create-intention).*
**NEEDS VERIFICATION:** Pakistan (`docs.paymob.pk` no longer resolves as of 2026-07-15); if Pakistan support is needed, confirm the current base URL with Paymob support.

### Test vs Live mode
Same regional base URL for both modes; **the mode is selected purely by which keys and integration IDs you use** (`sk_test_` vs `sk_live_`, test vs live integration IDs). A test key with a live integration ID (or vice versa) fails with a 404 on intention creation. Go-live requires business verification/approval.
*Source: [Overview — Test vs. live environments](https://developers.paymob.com/paymob-docs/developers/checkout-experiences) ("Test and live use the same regional base URL... The mode is controlled by the keys and integration IDs you use").*

### Test credentials
Cards (all: holder "Test Account", expiry 01/39, CVV 123): Mastercard `5123456789012346` and `5123450000000008`, Visa `4111111111111111`. Test mobile wallet: number `01010101010`, MPin `123456`, OTP `123456`.
*Source: [Test Credentials](https://developers.paymob.com/paymob-docs/need-help/faq/test-credentials.md).*

---

## General payment-architecture terms (not Paymob-specific)

### Idempotency / idempotent webhook handler
Property that processing the same event twice has the same effect as processing it once. For webhooks: key the handler on a unique event identity (for Paymob: transaction ID + transaction type flags) and make the ledger write a no-op if that identity was already processed. Required because any webhook sender may deliver duplicates and because reconciliation polling can race with webhook delivery.
*Source: industry practice; see e.g. [Stripe webhook docs — "handle duplicate events"](https://docs.stripe.com/webhooks).* 

### Reconciliation polling
A scheduled job that finds locally-`pending` payments older than some threshold and asks the gateway for their true status (Paymob: Transaction Inquiry API, ideally by `merchant_order_id`). This is the safety net for the webhook-never-arrived case and the only way to resolve abandoned checkouts, since Paymob sends callbacks **only on success or decline** — an intention the customer abandoned generates no callback at all.
*Source: [Webhook overview — "Paymob sends the transaction callback only if the transaction succeeds or is declined"](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac).* 

### Transaction state machine
Explicit set of states a payment record moves through with allowed transitions only, e.g. `draft → pending → (paid | failed | expired)`, `paid → partially_refunded → refunded`, and for auth/capture: `authorized → (captured | voided | expired)`. Prevents illegal transitions like `failed → paid` when a late/duplicate callback arrives out of order.
*Source: general payment-engineering practice; Paymob's own flags (`pending`, `success`, `is_auth`, `is_captured`, `is_voided`, `is_refunded`) map onto these states — see [Transaction callbacks](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/transaction-callbacks).* 

### PCI-DSS scope avoidance
Never letting raw card data (PAN, CVV) touch your servers. Hosted checkout achieves this: card entry happens on Paymob's domain; you receive only masked data (`source_data.pan` is the **last 4 digits only**) and tokens. Paymob's own docs: "You don't need to handle sensitive card data yourself."
*Source: [Overview](https://developers.paymob.com/paymob-docs/developers/checkout-experiences); masked pan visible in all callback samples.*

### Signature verification as a security boundary
The webhook endpoint is a public, unauthenticated URL — anyone who discovers it can POST arbitrary JSON. The HMAC (computed with a secret only you and Paymob know) is the *only* thing that proves a callback came from Paymob and wasn't tampered with. Every code path that mutates financial state must sit *behind* a successful HMAC check.
*Source: [HMAC overview](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/hmac); [Transaction callbacks — Caution note](https://developers.paymob.com/paymob-docs/developers/webhook-callbacks-and-hmac/transaction-callbacks).* 

### Audit log
Append-only record of every gateway interaction (request, callback, verification result, resulting ledger action). In Frappe, the conventional vehicles are the **Integration Request** doctype or a custom log doctype (the Ecosire connector uses a `Paymob Transaction` doctype "logging every auth, capture, wallet charge, BNPL settlement, and refund for audit").
*Source: [Ecosire — Paymob Gateway for ERPNext](https://ecosire.com/apps/erpnext/erpnext-paymob-gateway).* 

---

## ERPNext-side terms

### Payment Request
ERPNext doctype representing "we asked the customer to pay X against document Y (Sales Invoice/Sales Order)". Natural anchor for a gateway integration: create intention when the Payment Request is initiated, store the Paymob order/intention IDs against it, use its name as `special_reference`.
*Source: [ERPNext Payment Request docs](https://docs.frappe.io/erpnext/user/manual/en/payment-request).* 

### Payment Entry
ERPNext doctype that actually moves money in the ledger (GL entries) and allocates the amount against invoice outstanding. The verified-success webhook is what should trigger Payment Entry creation + submission.
*Source: [ERPNext Payment Entry docs](https://docs.frappe.io/erpnext/user/manual/en/payment-entry).* 

### payments app / Payment Gateway doctype
Frappe's separate `payments` app (github.com/frappe/payments) hosts gateway controllers (Stripe, Razorpay, ...) and the **Payment Gateway** doctype that Payment Request links to. A custom Paymob app can register itself the same way so Payment Requests can offer "Pay with Paymob".
*Source: [frappe/payments repository](https://github.com/frappe/payments).* 

### Payment Reconciliation
ERPNext tool/process matching unallocated Payment Entries against invoice outstanding amounts. Distinct from *gateway* reconciliation (polling Paymob for stuck intents) — the integration needs both meanings kept straight.
*Source: [ERPNext Payment Reconciliation docs](https://docs.frappe.io/erpnext/user/manual/en/payment-reconciliation).* 
