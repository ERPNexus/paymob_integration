# Must-Have Features — Non-Negotiables for the Paymob ↔ ERPNext Integration

Each feature is tagged with WHY it is required — the concrete failure that occurs without it. Cross-checked against Paymob's official docs and the feature set advertised by an existing commercial connector (Ecosire's "Paymob Gateway for ERPNext"); see `references.md`.

## Security

1. **HMAC-SHA512 verification on every callback (processed, response, and card-token), before any other processing.**
   WHY: the webhook endpoint is a public, unauthenticated URL. Without HMAC verification, anyone who discovers it can POST a forged `{"success": true}` payload and mark unpaid invoices as paid — direct financial fraud. Paymob's own docs warn: "In order to verify that these requests are received from Accept's endpoint, you have to implement the HMAC authentication."

2. **Secrets stored encrypted, never in code or plaintext fields.**
   WHY: the secret key can move money (refunds) and the HMAC secret is the entire forgery defense; a leaked pair means an attacker can both fake callbacks and issue refunds to arbitrary cards. Use Frappe `Password`-type fields (encrypted at rest) in a Settings doctype; never log them. (Ecosire advertises exactly this: "API key, HMAC secret, and per-country/per-method integration IDs in Frappe encrypted fields".)

3. **No raw card data anywhere (PCI scope avoidance).**
   WHY: storing PAN/CVV puts the ERPNext server in PCI-DSS scope — an audit and liability burden no ERP deployment wants. Hosted Unified Checkout keeps card entry on Paymob's domain; the integration must only ever persist masked data (`source_data.pan` = last 4) and tokens.

4. **Role-gated refund and configuration access.**
   WHY: a refund button callable by any user is an internal-fraud vector; whoever can edit the webhook URL or keys can redirect or forge payment confirmations. Dedicated role for refund/replay/settings (Ecosire: "Dedicated role and role profile gating secret visibility, refunds, and transaction replay").

## Correctness

5. **Idempotent webhook processing (dedup on transaction ID + event kind).**
   WHY: duplicate delivery must be assumed (undocumented retries, reconciliation poller racing the webhook, replays). Without dedup, one payment creates two submitted Payment Entries — the invoice shows overpayment, the ledger is wrong, and finance reconciles by hand.

6. **Explicit transaction state machine with legal-transition enforcement.**
   WHY: callbacks and poll results can arrive out of order or stale. Without `pending → paid | failed | expired` and refund transition rules, a late duplicate can flip a `paid` record to `failed` (or worse, a `failed` one to `paid`), and nothing stops double-processing.

7. **Unique `special_reference` per payment attempt, persisted with intention ID + Paymob order ID before redirecting the customer.**
   WHY: this is the correlation and idempotency key on the *outbound* side. If the intention IDs aren't stored before redirect and the server restarts, an incoming callback can't be matched to its invoice — an orphaned payment. Uniqueness also prevents accidentally creating two live Paymob orders for the same Payment Request.

8. **Server-side amount/currency verification on callback.**
   WHY: trust but verify — the ledger write must use `amount_cents` and `currency` from the *verified callback* (and check they match the expectation stored at intention time), never values echoed from the browser redirect. A mismatch must block auto-posting and flag for review.

## Resilience

9. **Reconciliation polling for stuck/pending intents (scheduled job → Transaction Inquiry API).**
   WHY: two guaranteed real-world gaps. (a) Paymob documents **no webhook retry policy** — if your endpoint is down for a deploy, that callback may simply be lost. (b) Paymob sends callbacks **only on success or decline**, so an abandoned checkout produces silence; without polling, those records stay `pending` forever and the invoice stays blocked. Ecosire ships this: "Scheduler events (hourly/daily) that reconcile pending, timed-out, or stuck intents automatically." Poll results must flow through the same idempotent update path as webhooks.

10. **Intention expiry handling.**
    WHY: an intention created with `expiration: 3600` that's never paid must eventually transition to `expired` locally so the customer can retry with a fresh intention and finance doesn't chase ghosts.

11. **Webhook endpoint returns 2xx fast and defers heavy work.**
    WHY: ledger creation inside the request handler risks timeouts; with retry behavior undocumented, a timed-out (but actually processed) callback is indistinguishable from a lost one on Paymob's side. Verify HMAC + persist + enqueue (`frappe.enqueue`), respond immediately.

## Financial operations

12. **Refund (full + partial) initiated from ERPNext, with ledger write-back.**
    WHY: refunds *will* happen; if staff do them in the Paymob dashboard instead, ERPNext's books diverge from reality until someone notices. The integration calls `void_refund/refund`, then posts the reversing entry from the resulting verified callback — handling multiple partial refunds and signed child-transaction deltas correctly.

13. **Automatic Payment Entry creation + allocation against Sales Invoice / Sales Order / Payment Request.**
    WHY: this is the entire point of the integration — a verified payment that a human still has to key in manually is just an expensive notification. On verified success: Payment Entry (Receive), correct account, allocated against outstanding, submitted.

14. **Multi-currency and amount-in-cents discipline.**
    WHY: Paymob amounts are integers in cents; ERPNext amounts are decimals in currency units. One missed `/100` posts a 100× wrong payment. Currency of intention must match the integration ID's currency, and Payment Entry must use the invoice's currency/exchange rate rules.

## Observability & configuration

15. **Durable transaction history plus an exception-and-accountability ledger.**
    WHY: Payment Attempts, Paymob Transactions, Payment Entries, and logs preserve routine processing evidence. Audit Entries stay focused on anomalies requiring human attention and on who requested refunds, so the review queue remains actionable.

16. **Settings doctype with per-country credential sets and test-mode switch.**
    WHY: Egypt/KSA/UAE/Oman are separate Paymob accounts with separate base URLs, keys, and integration IDs — hardcoding one set caps the integration at one country. A visible test/live mode flag prevents the classic incident of live keys in a staging site (or test keys silently in production, where every "payment" succeeds with card 5123...2346).

17. **Clear customer-facing result page driven by verified state, not raw redirect params.**
    WHY: the redirect can be absent, delayed, or manipulated. The page should show the payment's locally verified status (or verify the redirect's own HMAC before trusting its params) — otherwise customers see "success" for payments the system will never confirm.

## Explicitly out of "must", worth noting

- **Card tokenization / saved cards, subscriptions, BNPL method surfacing** — valuable (Ecosire advertises all three) but additive; they ride on the same intention + callback + HMAC machinery and can come after the core is solid.

## Areas the docs do NOT settle — test empirically before trusting

- **Webhook retry/redelivery behavior**: nothing documented. Assume zero retries; prove otherwise with a deliberately-failing endpoint in test mode.
- **Rate limits** on the Intention and Inquiry APIs: not documented. Matters for the reconciliation poller's batch size.
- **Auth-token lifetime** for the Inquiry API: not documented in current pages (folklore says ~1 hour). Handle 401 + re-auth regardless.
- **Sandbox-vs-live parity**: whether test mode fires callbacks with identical timing/shape to live (esp. wallets/BNPL) is unverified — validate the full webhook + HMAC path in test mode *and* again with a small live transaction before go-live.
- **GET redirect param naming** (`order` vs `order_id`) in the response-callback HMAC input: docs and sample disagree; log a real redirect and confirm.
