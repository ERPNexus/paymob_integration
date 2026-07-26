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
turns Paymob off *everywhere*. Turning off one credential row below only turns off *that one
country*. Turning off one payment-method row only turns off *that one payment method*.

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

Use **Paymob Attempts** on the same Payment Request to see each checkout try. If a card is declined,
start a new payment; the previous attempt remains as history.

**Audience:** the merchant / ERPNext user operating Paymob payments.

Plain-language, task-oriented docs — how to *use* the app, no code. Written as features ship
(per [../../rules/documentation.md](../../rules/documentation.md)). Describe behavior in prose and
link into [../reference/](../reference/) for the exact rules rather than restating them.

## Planned topics (filled as slices land)

- Connecting a Paymob account (credentials, test vs live).
- Choosing which payment methods to offer.
- What each payment status means to you (links to [states](../reference/states.md)).
- What "needs review" means and how to resolve it.
- Reading a payment's history and reconciling.
