# User Guide

## Configure Paymob

As a System Manager, open **Paymob Settings**. This screen has one field of its own, plus two
tables. Each table has its own fields. This section explains every field, what it does, and where
to find the value in your Paymob dashboard.

### Paymob Settings (the main screen)

| Field | What it does |
|---|---|
| **Enabled** | The master switch for the whole app. Turn this on only after your credentials and payment methods are configured and tested below. While it is off, no payment can be started. |
| **Mode** | Choose **Test** or **Live** for the whole site. Test mode uses fake money, so you can try the flow safely. Live mode charges real customers. Paymob never falls back from Live to Test — if your Live credentials are missing or wrong, payments fail, they do not quietly switch to Test. |
| **Intention Expiration Seconds** | How many seconds a checkout link stays valid before it expires. Default is 3600 (one hour). If a customer opens the checkout page after this time, they must start again. |
| **Stale Pending Minutes** | How many minutes a payment can stay "pending" before the system checks with Paymob to find out what really happened. Default is 20. This is a safety net for payments where Paymob's confirmation message never arrives. |

A word on "**Enabled**": you will see this same checkbox three times — once here, once on each
credential row, and once on each payment-method row. They do not all mean the same thing. This one
turns Paymob off *everywhere*, including checkout, refunds, callbacks, scheduled
reconciliation, and their Payment Request buttons. Turning off one credential row below only turns
off *that one country*. Turning off one payment-method row only turns off *that one payment method*.

### Credential Sets (the first table)

Add one row per **country**, **currency**, and **mode** combination you accept payments in. Paymob
treats each country as a fully separate account, so a row for Egypt cannot be reused for Saudi
Arabia — you need a separate row, with its own keys, for each.

| Field | What it does | Where to find it |
|---|---|---|
| **Enabled** | Turns this one country/currency/mode combination on or off, without touching any other row. | — |
| **Country** | The country this row's Paymob account belongs to. | You choose this to match your Paymob account (e.g. Egypt, Saudi Arabia). |
| **Currency** | The currency this row charges in (e.g. EGP, SAR). | Must match the currency your Paymob integration IDs for this row use. |
| **Mode** | Test or Live, for this row only. Keep a separate row for each — never edit a Live row into a Test row or the other way around. | — |
| **Base URL** | The web address of the Paymob servers for this country. Every country has a different one. | Paymob's API documentation lists one base URL per region, e.g. `https://accept.paymob.com/` for Egypt. |
| **Public Key** | A key that is *safe* to send to the customer's browser. It only identifies your account to Paymob's checkout page — nobody can use it to move money. | Paymob dashboard → Developers → your integration, labeled "Public Key" (`pk_test_...` or `pk_live_...`). |
| **Secret Key** | A server-only key used to create and manage payments. Never shown again after you save it, and never sent to the browser. | Paymob dashboard → Developers, labeled "Secret Key" (`sk_test_...` or `sk_live_...`). |
| **API Key** | A server-only key used to prove who you are when *checking* a payment's status. Unlike the other keys, Paymob uses the same API Key for both Test and Live. | Paymob dashboard → Settings tab, labeled "API Key". |
| **HMAC Secret** | A server-only key used to check that a message claiming to be "from Paymob" really is from Paymob, and was not faked or altered. | Paymob dashboard → Developers, labeled "HMAC Secret". |
| **Payment Account** | The ERPNext ledger account that receives the money once a payment is confirmed. | Choose an existing Account in your Chart of Accounts (for example, a "Paymob Clearing Account"). |

**Secret Key**, **API Key**, and **HMAC Secret** are stored encrypted and are never shown on
screen again once saved, never logged, and never sent to a browser. **Public Key** is the one
exception — it is designed to be public, so it is stored as plain text.

### Integration IDs (the second table)

Add one row per **payment method** you want to offer (for example, card payments, or a mobile
wallet), for each country/currency/mode combination.

| Field | What it does | Where to find it |
|---|---|---|
| **Enabled** | Turns this one payment method on or off, without touching the others. | — |
| **Country** / **Currency** / **Mode** | Same meaning as on the credential-set row above — this payment method belongs to one country, one currency, one mode. | Must match one of your Credential Set rows, or there is nothing to charge against. |
| **Payment Method** | A short name you choose to remember what this row is for (e.g. "Card", "Wallet"). It is a label for you — Paymob never sees this text. | Your own choice. |
| **Integration ID** | The number Paymob assigns to one payment-method configuration in your dashboard. This is the value actually sent to Paymob when a checkout is created. | Paymob dashboard → Developers → Payment Integrations, next to the payment method you configured there. |

### Connecting Paymob's callback

In your Paymob dashboard, under the integration this credential row uses, paste ERPNext's webhook
address into the **Transaction Processed Callback** field — not the **Transaction Response
Callback** field, which is a different, browser-facing setting ERPNext also uses but that carries
no authority to record a payment. The HMAC secret you paste into **HMAC Secret** above must be the
one for that same Paymob account, or every callback from it is silently refused (rejected, no
payment from that account ever recorded) with no explanation sent back to Paymob.

### Immediate payments

Every enabled **Integration ID** must be configured in the Paymob dashboard for immediate or
standalone payment. A verified standalone success moves the attempt to **Paid** and creates one
allocated Payment Entry. Unsupported signed events are stored for review and do not change money
or state.

### Testing your setup

Click **Test Connection**, choose a currency, and wait for a green success message. This proves
your **API Key** is correct and Paymob accepted it — it does not create a real payment or move any
money. Do this for every currency you configure, and fix any row that fails before you turn on the
site-wide **Enabled** switch. Keep separate Test and Live rows, and do not screenshot or share
Secret Key, API Key, or HMAC Secret with anyone outside your team.

## Take a payment

Open a submitted **Payment Request** and click **Pay with Paymob**. ERPNext opens Paymob's hosted
checkout in a new tab. The Payment Request's company and currency select the matching Paymob
credentials. Customer billing details use the linked document's selected address when available,
then the customer's primary address.

Use **Paymob Attempts** on the same Payment Request to see each checkout try. A decline remains in
the history, but Paymob may still confirm that same unexpired checkout afterward; only a verified
matching success records the payment. Starting checkout from Desk intentionally creates a new try.

By default, ERPNext emails the payer a signed payment link when you submit an incoming Payment Request.
Opening that link in multiple tabs reuses one ready checkout; it opens a fresh one only after expiry.
Turn off **Send Payment Link Email** in Paymob Settings to disable this site-wide, or use the request's
existing **Mute Email** option for one request.

Paymob payment alerts are editable native **Notifications**. Open **Notifications** in Desk to edit their
recipients, content, or enabled state. They are on by default for payment received, failure, expiry,
refunds, review-needed audit entries, and refund request activity. The linked Payment
Request's Company appears in customer-facing email branding; your configured site **Email Account**
controls the actual From address and display name.

## Reconciliation and refunds

Pending attempts are periodically checked with Paymob when a processed callback is lost. A verified
inquiry result follows the same amount, currency, duplicate, and ledger rules as a callback. An
authentic mismatch is recorded for review and never posts automatically.

From a paid attempt, an authorized user may request a partial or full refund. The app locks the
attempt before making the one outbound request and waits for Paymob's signed refund callback before
creating the reversal entry. Do not resend a refund after a timeout; investigate the Paymob result
and make any second request a deliberate human decision.

For reproducible acceptance evidence, use the [sandbox smoke-test checklist](../developer-guide/sandbox-smoke-test.md).

## What the customer sees after paying

Paymob sends the customer's browser back to a simple status page. It can say "we're confirming
your payment" even for a payment that has already gone through — the real confirmation travels
directly between Paymob's servers and ERPNext, and that message can arrive a moment before or
after the customer's browser redirect does. This is normal, not a stall or a bug, and needs no
action from you. The status the customer sees always matches what ERPNext has recorded, once both
messages have arrived. See [states.md](../reference/states.md) for what each status means.

## What happens if a payment goes missing

Sometimes Paymob's confirmation message never reaches ERPNext — a network hiccup, a server
restart, anything. You do not need to do anything about this: every 15 minutes, ERPNext quietly
asks Paymob directly what happened to any payment that has been "pending" for a while (see
**Stale Pending Minutes** above). If Paymob confirms the payment actually went through, ERPNext
records it exactly as if the original message had arrived — the Payment Request still ends up
**Paid**, with a normal Payment Entry. If Paymob confirms nothing was ever charged and the
checkout link's time is up, the attempt is marked **Expired** instead, so the customer can start a
fresh attempt. Either way, nothing is guessed from a failed or slow connection to Paymob — if
Paymob cannot be reached, the payment is simply checked again at the next 15-minute pass.

## Refund a Paymob payment

A user granted **Paymob Refund Manager** can open a paid Payment Request and choose **Refund**
(full or partial). ERPNext sends one request to Paymob, then waits for Paymob's signed
confirmation before posting the reversing entry. If a request remains in progress after a network
error, do not send it again: Paymob may still have received it. Review the linked audit entry.
