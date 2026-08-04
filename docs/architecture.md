# Architecture — How a Paymob ↔ ERPNext Payment Actually Flows

This is a data-flow narrative of one payment, from "customer clicks Pay" to "ERPNext ledger is correct", including the failure paths. Terms are defined in `glossary.md`; sources in `references.md`.

```
ERPNext backend                Paymob                        Customer browser
──────────────                 ──────                        ────────────────
1. Payment Request
2. POST /v1/intention/  ──────▶ creates intention + order
   (Token sk_..., amount,      ◀── client_secret, order id
    special_reference,
    notification_url,
    redirection_url)
3. store IDs, state=pending
4. build checkout URL   ─────────────────────────────────▶ 5. redirected to
                                                              {base}/unifiedcheckout/
                                                              ?publicKey=pk_..
                                                              &clientSecret=egy_csk_..
                               6. hosted page collects card,
                                  runs 3-D Secure challenge,
                                  authorizes with the bank
        ┌──────────────────────┴───────────────────────────────┐
        ▼ (server-to-server)                                    ▼ (browser)
7a. Transaction PROCESSED callback                 7b. Transaction RESPONSE callback
    POST JSON {"type":"TRANSACTION","obj":{...}}       GET redirect w/ query params
    + ?hmac=... on your URL                            + &hmac=...
8. verify HMAC-SHA512  ──reject──▶ log & 401       8b. verify HMAC, show
9. idempotency check   ──dup────▶ ack & exit           "payment succeeded/failed"
10. state machine transition                            page ONLY (no ledger write)
    pending → paid | failed
11. create + submit Payment Entry
    against the Sales Invoice
12. audit only exceptions requiring attention and human money-movement requests

13. (scheduler, every N minutes) reconciliation poll:
    for each stale 'pending' record →
    POST /api/ecommerce/orders/transaction_inquiry {merchant_order_id}
    → apply same verified-update path as step 10–12, or expire it
```

## 1–3. Checkout initiation (backend only)

The trigger is an ERPNext document that expects money — canonically a **Payment Request** against a Sales Invoice or Sales Order. The backend (never the browser) calls:

```
POST {regional_base}/v1/intention/
Authorization: Token sk_test_...      ← secret key, matching mode
{
  "amount": <in cents>, "currency": "EGP",
  "payment_methods": [<integration_id>, ...],
  "items": [...], "billing_data": {...},          ← phone_number, email, names required
  "special_reference": "<Payment Request name>",  ← comes back as merchant_order_id
  "notification_url": "<our webhook>",            ← card integrations only
  "redirection_url": "<our thank-you page>",
  "expiration": 3600
}
```

The response gives three identifiers to persist immediately, *before* the customer sees anything: the intention `id` (`pi_...`), `intention_order_id` (Paymob's order ID — the primary correlation key in callbacks), and `client_secret`. The local payment record enters state **pending**.

Why `special_reference` matters twice: (a) it lets a callback be matched back to the exact ERPNext document without a lookup table, and (b) since Paymob requires it to be unique, re-submitting the same reference cannot silently create a second live order for the same invoice.

## 4–6. Customer pays on Paymob's turf

The browser is sent to `{base}/unifiedcheckout/?publicKey=pk_...&clientSecret=...`. Everything sensitive — card entry, 3-D Secure OTP challenge, bank authorization — happens on Paymob's hosted page. This is the PCI-scope boundary: ERPNext never sees a full PAN or CVV, only the masked `source_data.pan` (last 4) later in the callback. The client secret ties the session to exactly one intention, so amounts can't be tampered with client-side.

## 7. Two callbacks race back — and they are not equals

When the transaction **succeeds or is declined** (only then — an abandoned checkout sends *nothing*), Paymob fires two channels:

| | Processed (webhook) | Response (redirect) |
|---|---|---|
| Transport | `POST`, JSON body, server→server | `GET`, query params, via customer's browser |
| Reliability | Arrives even if browser dies | Arrives only if the customer's browser completes the redirect |
| Role | **Source of truth** → ledger updates | UX only → render result page |

Both carry an `hmac`. Both must be verified. But only the processed callback may mutate financial state; the redirect can be spoofed by the customer simply editing the URL (even with valid-looking params, the customer controls delivery), and it may never arrive. Conversely, the webhook can beat the redirect or lose the race — the result page should therefore read the *locally stored* state (or verify its own params) rather than assume the webhook already landed.

## 8. HMAC verification — the security boundary

The webhook endpoint is a public URL. The only proof a payload is genuinely Paymob's is the HMAC: concatenate the 20 documented field values in lexicographic key order (`amount_cents, created_at, currency, error_occured, has_parent_transaction, id, integration_id, is_3d_secure, is_auth, is_capture, is_refunded, is_standalone_payment, is_voided, order.id, owner, pending, source_data.pan, source_data.sub_type, source_data.type, success` — booleans as lowercase `true`/`false`), HMAC-SHA512 with the dashboard HMAC secret, hex lowercase, constant-time compare against the received `hmac` query param. Failure → log, return an error, touch nothing.

Note the field-name mapping differs by callback type: `obj.id`/`obj.order.id` in the POST JSON vs flat `id`/`order` params in the GET redirect (docs say `order_id`; sample URL shows `order` — verify empirically).

## 9–10. Idempotency, then the state machine

Even with no documented retry policy, duplicates must be assumed: the reconciliation poller can
race the webhook and any network layer can replay. So before acting:

1. **Dedup**: has (transaction id `obj.id` + event kind derived from the flags) been processed? If yes, acknowledge and stop.
2. **State machine**: is the transition legal? `pending → paid` (verified standalone success),
   `pending → failed` (decline), and `paid → partially_refunded/refunded` (signed refund delta).
   A `failed` record must never move to `paid` off a stale duplicate, and a second success callback
   must not create a second Payment Entry.

The flags in the payload are how you classify the event — there is no separate "event type" field beyond `type: "TRANSACTION"`; a refund notification is the *parent* transaction re-sent with `is_refunded: true`, and the refund itself is a child transaction with `is_refund: true` and `parent_transaction` set.

## 11–12. ERPNext ledger update

On a verified, deduplicated success:

- Locate the source document via `merchant_order_id` (= `special_reference` = e.g. the Payment Request name); fall back to the stored Paymob order ID.
- Create and submit a **Payment Entry** (Receive) for `amount_cents / 100`, allocated against the Sales Invoice's outstanding, using the gateway's clearing/receivable account. Payment Request has built-in machinery for exactly this (`on_payment_authorized` in the payments-app pattern).
- Keep the gateway event in **Paymob Transaction**. Create a **Paymob Audit Entry** only for an
  anomaly requiring human attention; routine successful processing is already visible through the
  transaction, attempt, Payment Entry, and application log.

Refund flow mirrors this in reverse: a refund initiated from ERPNext calls `POST /api/acceptance/void_refund/refund {transaction_id, amount_cents}`, and the resulting callback (parent with `is_refunded: true`) drives creation of the reversing Payment Entry — again idempotently, because partial refunds mean several such callbacks with growing `refunded_amount_cents`.

Signed Auth, Capture, and Void flags are retained only for HMAC verification and redacted callback
storage. They are classified as `Unsupported`, audited for review, and never mutate the ledger.

## 13. Reconciliation polling — the safety net

Two gaps make polling non-optional:

1. **Webhook never delivered** (endpoint down, network issue, misconfigured URL). Paymob's docs do not document any retry/redelivery behavior — treat redelivery as nonexistent until proven otherwise.
2. **Customer abandoned checkout**. No callback of any kind fires, so the local record stays `pending` forever without intervention.

A scheduler job (Frappe `scheduler_events`, e.g. every 15–30 min) selects local records stuck in `pending` beyond a threshold and calls the Transaction Inquiry API — `POST /api/ecommerce/orders/transaction_inquiry` with `merchant_order_id` is the convenient form since it uses your own reference. The result feeds the *same* state-machine + Payment-Entry path as a webhook would (which is why that path must be idempotent). Records past the intention's `expiration` with no transaction get closed as `expired`, freeing the invoice for a new payment attempt.

Inquiry auth is the odd one out: it needs a **Bearer auth token** obtained from `POST /api/auth/tokens {"api_key": ...}`, not the secret key.

## Multi-region note

Egypt, KSA, UAE, and Oman are separate Paymob deployments with separate merchant accounts, keys, integration IDs, and base URLs. An integration serving more than one country needs per-country credential sets (base URL + secret/public/API keys + HMAC secret + integration IDs) and must route each payment by the invoice company's country and the transaction currency — one global settings record with a single key set cannot work.
