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
