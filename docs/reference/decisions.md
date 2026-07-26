# Decisions (ADRs)

The *why* behind non-obvious choices. Newest entries appended with the next number. Format:
context → decision → consequences. Governed by [../../rules/documentation.md](../../rules/documentation.md).

---

### ADR-0001 — Ledger writes are triggered only by the server-to-server processed callback

**Date:** 2026-07-21 · **Status:** Accepted

**Functional:** The customer's browser never causes money to be recorded. Even if the customer
closes the browser, the payment is still recorded correctly.

**Technical:**
- **Context:** After checkout, ERPNext receives payment info via **two independent channels** —
  a server-to-server **processed callback** (POST from Paymob) and a **response callback**
  (a GET the customer's browser makes). Both can carry a valid HMAC.
- **Decision:** Only the **processed callback** may trigger a Payment Entry. The browser
  response callback is **UX only** — it shows a result page and writes nothing to the ledger.
- **Consequences / why:**
  - *Reliability:* the server-to-server channel is guaranteed to arrive; the browser channel can
    be closed or interrupted.
  - *Security:* the browser channel runs on the user's device and can be **replayed** — a valid
    HMAC proves "Paymob said this once," not that it is fresh or for this order. A captured
    old success could be replayed against a new order if the browser callback were trusted.
  - The result page must therefore be **generic** ("we're confirming…"), because the browser
    can arrive before the processed callback finishes — the two channels can race.

---

### ADR-0002 — Server-only credentials never reach the browser

**Date:** 2026-07-21 · **Status:** Accepted

**Functional:** Only two harmless identifiers are ever sent to the customer's browser; the
credentials that could forge payments stay on the server.

**Technical:**
- **Context:** Paymob issues secret key, API key, HMAC secret, public key, and a per-checkout
  client secret. The question at every step is *does this run on our server or in the browser?*
- **Decision:**
  - **Browser-safe:** `public key` (identifies the merchant only) + `client secret` (unlocks one
    checkout session only).
  - **Server-only, never exposed:** `secret key` (create intention), `API key` (→ auth token →
    inquiry), `HMAC secret` (verify callbacks).
- **Consequences / why:** exposing any server-only credential enables forged payments or forged
  server requests. A leaked client secret risks a single session, not the account. Reviewers must
  **reject** any generated code that sends a server-only credential to the browser.

---

### ADR-0003 — Authentic amount mismatch is audited, never auto-posted

**Date:** 2026-07-21 · **Status:** Accepted

**Functional:** If Paymob authentically reports a different amount than we expected, we do not
silently accept it — a human reviews it before it hits the books.

**Technical:**
- **Context:** A callback can be authentic (valid HMAC) yet report an amount ≠ the immutable
  amount snapshotted at intention creation. Authenticity ≠ business correctness.
- **Decision:** Preserve and audit the authentic mismatch, **block automatic Payment Entry
  creation**, and raise the [`needs_human_attention`](states.md#needs_human_attention) flag. The
  lifecycle state is not regressed.
- **Consequences / why:** protects the ledger from posting the wrong amount while still keeping a
  full, tamper-evident record for reconciliation.

---

### ADR-0010 — The `payments` app is not a dependency

**Date:** 2026-07-26 · **Status:** Accepted

**Functional:** Installing this app does not require installing another payment app.

**Technical:**
- **Context:** ERPNext's Payment Request gateway machinery resolves controllers through the
  `Payment Gateway` DocType in the separate `payments` app, which is not installed on this bench.
- **Decision:** Drive Payment Requests directly. Paymob configuration lives in `Paymob Settings`,
  and `Paymob Credential Set.payment_account` supplies the clearing account.
- **Consequences / why:** this removes a dependency and indirection. Phase 02 supplies the
  Pay with Paymob button; installing `payments` later does not conflict with this setup.

---

### ADR-0004 — Lifecycle state lives on a Paymob Payment Attempt, not on the Payment Request

**Date:** 2026-07-26 · **Status:** Accepted

**Functional:** A declined checkout stays visible while the customer starts a separate retry.

**Technical:** One `Paymob Payment Attempt`, named by its unique `special_reference`, stores the
frozen amount, state, and Paymob identifiers for each checkout. Payment Request status remains
derived from submitted Payment Entries. This preserves retry history and makes the unique reference
the outbound correlation guarantee.

---

### ADR-0011 — The result page resolves the credential set before verifying the redirect signature

**Date:** 2026-07-26 · **Status:** Accepted

**Functional:** The result page can find the right secret to check, for every country Paymob
accounts are configured in, without guessing.

**Technical:**
- **Context:** `rules/implementation-gate.md` §2 requires verification before any database
  access. But the HMAC secret is stored per country/currency on `Paymob Credential Set`, and the
  only place that pairing is recorded for a given checkout is the `Paymob Payment Attempt` row
  itself — there is no way to pick the right secret without a lookup first.
- **Decision:** Load the attempt with a read-only `frappe.db.get_value` (four non-sensitive
  columns, no `get_doc`, no `client_secret`), resolve its credential set, then verify. The
  alternative — trial-verifying the signature against every enabled credential set until one
  matches — still reads the database (every row instead of one) and adds branching for no
  security benefit, since a wrong-secret trial and a genuine forgery look identical either way.
- **Consequences / why:** the exception is bounded to this page, which has no ledger authority
  (ADR-0001) and performs no write in any branch. It does not license "load then verify" on any
  path that can move money — those paths still verify strictly first, per gate §2.

---

### ADR-0006 — The processed callback is the app's only `allow_guest=True` method

**Date:** 2026-07-26 · **Status:** Accepted

**Functional:** Paymob's servers can tell us a payment succeeded without a customer being logged
in to ERPNext — because the message never comes from a customer's browser.

**Technical:**
- **Context:** `rules/payments.md` rule 17 makes `allow_guest=True` on a money-moving method an
  automatic reject, because a guest endpoint has no permission check to lean on. The processed
  callback is money-moving (ADR-0001: it is the *only* channel with ledger authority) and must be
  `allow_guest=True`, because Paymob's servers hold no Frappe session and can never obtain one.
- **Decision:** This is the one deliberate, narrow exception. It is safe because the endpoint does
  no work "as" any identity — it does not read, write, or return anything document-specific until
  the HMAC-SHA512 signature is verified, and the signature *is* the authentication. Every other
  money-moving `@frappe.whitelist()` method in the app checks permission on the document first, as
  rule 17 requires.
- Resolving the HMAC secret reads `Paymob Settings` (`settings.enabled_credential_sets()`)
  *before* verification succeeds or fails. This looks like it violates gate §2 ("verify before any
  database access"), but it does not: §2 forbids reading the **business document the payload
  names** before verification — here, no attempt, Payment Request, or any payload-named document
  is loaded. Reading **configuration to obtain the key needed to verify** is part of verifying, not
  a bypass of it. This is narrower than [ADR-0011](#adr-0011--the-result-page-resolves-the-credential-set-before-verifying-the-redirect-signature),
  which reads one payload-named attempt row before verifying on a page with no ledger authority at
  all — the processed callback loads no attempt here, in this phase or any later one, until after
  a matching secret is found.
- **Consequences / why:** a forgery matches no configured secret and is refused with a `401` that
  carries no explanation and touches no document. A genuine callback matches exactly one
  credential set, at which point acting "as" the merchant account that set matches is exactly what
  should happen. No other endpoint in this app may follow this pattern.
