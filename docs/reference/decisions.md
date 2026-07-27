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
- **Implementation:** `paymob.processor.process_transaction` (Phase 07), gated to `target ==
  "Paid"` only — a `Refund` carries a deliberately partial amount and is not compared here.
  `amounts.amounts_match` takes both amounts *and* both currencies, since the right number in the
  wrong currency is a mismatch too. A mismatch sets `attempt.needs_human_attention = 1` and writes
  one `Amount Mismatch` audit entry with both cents and both currencies; the lifecycle state still
  advances to `Paid` per [states.md](states.md#needs_human_attention) — the flag is orthogonal, not
  a regression. No Payment Entry exists yet to block; that gate is
  [ADR-0008](#adr-0008--the-in-memory-payment_account-assignment-and-a-post-hoc-amount-check),
  reading this flag.

---

### ADR-0008 — The in-memory `payment_account` assignment and a post-hoc amount check

**Date:** 2026-07-27 · **Status:** Accepted

**Functional:** The clearing account a Paymob payment lands in comes from the Paymob credential
configuration, not from a value stored on the Payment Request itself — and the posted amount is
checked against what Paymob actually confirmed, even though ERPNext computes it independently.

**Technical:**
- **Context:** `PaymentRequest.create_payment_entry(submit=True)` reads `self.payment_account` as
  the `bank_account` argument to `get_payment_entry(...)`
  (`erpnext/accounts/doctype/payment_request/payment_request.py:348`), then calls
  `_allocate_payment_request_to_pe_references` (`:505`, which sets
  `references[0].payment_request = self.name`) and submits. `Paymob Credential Set.payment_account`
  is the only place this app stores a clearing account (ADR-0010); the Payment Request DocType has
  no field for it.
- **Decision:** `paymob.ledger.post_payment` fetches the Payment Request with `for_update=True`
  before its duplicate-Payment-Entry lookup, then sets `payment_request.payment_account =
  credentials.payment_account` on the **in-memory** document, immediately before calling
  `create_payment_entry(submit=True)`, and never saves that assignment. It then compares the
  posted amount (converted to minor units) against `transaction.amount_cents` and raises — rolling
  back the whole write — on any mismatch. The posted amount is read from whichever Payment Entry
  side is actually denominated in `transaction.currency` — `received_amount`
  (`paid_to_account_currency`, the clearing-account side this decision just set) if that matches,
  else `paid_amount` (`paid_from_account_currency`, the party/company side) — not `paid_amount`
  unconditionally, because the two differ whenever the Payment Request's party account isn't in
  the Payment Request's own currency.
- **Consequences / why:** `create_payment_entry` posts `self.outstanding_amount`, read *at call
  time*, not `attempt.expected_amount_cents` (a snapshot from intention creation, already checked
  by [ADR-0003](#adr-0003--authentic-amount-mismatch-is-audited-never-auto-posted)). If the Payment
  Request's outstanding amount moved between checkout and settlement — a partial cash payment, a
  credit note — the two snapshots can legitimately disagree even on an authentic, amount-matched
  callback. The post-hoc check is what actually guarantees "the ledger entry equals what Paymob
  collected" in production, not just in a test where nothing else touches the Payment Request in
  between. `PaymentEntry.update_payment_requests` (`payment_entry.py:320`) derives Payment Request
  status from the submission itself — nothing in this app writes it directly.
  The `for_update` lock on the Payment Request (not just the caller's lock on the attempt) is what
  serialises two different attempts of the *same* Payment Request: a retry is a new attempt row
  (rules/payments.md), so `frappe.get_doc(..., for_update=True)` on the attempt alone does not
  block a second, concurrent verified success for a sibling attempt from reaching the duplicate
  check before the first one's Payment Entry is visible.

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

### ADR-0005 — The dedup key is the row's own primary key, not a separate unique column

**Date:** 2026-07-26 · **Status:** Accepted

**Functional:** The same webhook delivered twice never creates two records — Frappe's own
document-name uniqueness is the guarantee, not application code.

**Technical:**
- **Context:** `plans/05-transaction-record-and-dedup.md` called for a unique column holding
  `"<transaction_id>:<event_kind>"`. In Frappe a unique **field** collision raises
  `frappe.UniqueValidationError`; only a **primary-key** collision raises
  `frappe.DuplicateEntryError`, the exception `webhooks._store` is written to catch. A unique
  field would also add a second index for the same fact the primary key already indexes.
- **Decision:** `PaymobTransaction.autoname()` sets `self.name = f"{paymob_transaction_id}:
  {event_kind}"` directly — no `event_key` field exists on the DocType. `SHOW INDEX FROM
  \`tabPaymob Transaction\`` shows one `PRIMARY` index and nothing else.
- Also decided here: **`Pending` is a seventh event kind**, not folded into `Success`. Paymob's
  wallet/kiosk flow can send `pending: true, success: true`, followed later by a real settlement
  for the same transaction id. Classifying both as `Success` would give them the same computed
  name and silently swallow the settlement as a "duplicate."
- Also decided here: **`Refund`'s key includes `refunded_amount_cents`** —
  `f"{paymob_transaction_id}:Refund:{refunded_amount_cents}"`. Paymob resends the *same* parent
  transaction id for each cumulative partial refund with a growing `refunded_amount_cents`
  (`plans/11-refund-and-void.md`); keying on `event_kind` alone would collapse the second partial
  refund into the first's row instead of recording it. An exact resend (identical amount) still
  dedups correctly.
- **Consequences / why:** one index instead of two, the app's actual duplicate-guard exception
  matches the one `rules/payments.md` §6 names, a genuine settlement arriving after a pending
  notification is never lost, and cumulative partial refunds are never silently dropped.

---

### ADR-0007 — Persist-then-acknowledge: the `200` means committed

**Date:** 2026-07-26 · **Status:** Accepted

**Functional:** When Paymob's servers get a `200` back from the processed callback, the payment
event is already safely on disk — not just "read."

**Technical:**
- **Context:** Before this phase, `processed_callback` verified the HMAC and returned `"ok"`
  without writing anything — the `200` meant "we read it," not "we kept it." Paymob's webhook
  retry behaviour is undocumented and assumed to be zero (`plans/README.md`, decision 4), so a
  lost event between verification and storage had no other safety net.
- **Decision:** `webhooks._store` inserts the `Paymob Transaction` row and calls
  `frappe.db.commit()` **before** `processed_callback` returns `"ok"`. A duplicate delivery
  (`frappe.DuplicateEntryError`) also returns `"ok"` — the row already exists, so there is nothing
  left to acknowledge differently. Any other exception during insert is left to propagate: Frappe
  rolls back and the response is a 5xx, so Paymob (or the Phase 10 poller) retries.
- **Consequences / why:** the only exception `_store` catches is `frappe.DuplicateEntryError` — a
  broader `except` would silently swallow a real persistence failure while still telling Paymob
  "got it," burying the one event that needed to be kept. Because Paymob's own retry behaviour
  cannot be relied on, the Phase 10 poller is the real safety net for a delivery that gets a 5xx.

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

---

### ADR-0009 — Audit entries are submittable and immutable; a resolution is an append via `supersedes`

**Date:** 2026-07-26 · **Status:** Accepted

**Functional:** A record of "something needed a human's attention" can never be quietly edited or
deleted afterward — including by the person who resolves it. Resolving one writes a *new* record
that points back at the original.

**Technical:**
- **Context:** [`rules/audit-trail.md`](../../rules/audit-trail.md) requires that audit records
  are immutable and that "a correction is a new record that refers to the earlier one." A
  permission table (no `write`/`delete` role) can always be loosened by a future change or an
  administrator; it is discipline, not a guarantee.
- **Decision:** `Paymob Audit Entry` is `is_submittable: 1` with **no `amended_from` field** in
  its DocType JSON. Frappe's DocType-sync path (`frappe.modules.import_file.import_doc`) loads
  fixture JSON with `flags.ignore_validate = True`, so the framework's usual "add `amended_from`
  when `is_submittable`" step (`DocType.make_amendable`) never runs for a doctype whose schema is
  shipped this way — the field stays absent, and with no `amended_from` there is no Amend action
  to offer. Frappe itself refuses to write a submitted (`docstatus = 1`) document at the ORM
  level (`UpdateAfterSubmitError`), which is a stronger guarantee than a permission row an
  administrator could edit. No role is granted `write`, `delete`, `submit`, `cancel`, or `amend`
  on the doctype at all — every entry is inserted and submitted by server code
  (`paymob.audit.record`, see [ADR-0012](#adr-0012--the-audit-writer-moved-to-its-own-module))
  with `ignore_permissions=True`, and a resolution is recorded by inserting a **new** entry whose
  `supersedes` field names the one it resolves.
- **Decision:** The "needs action" view (`Paymob Open Audit Entries`) is a **Script Report**, not
  a Query Report as the Phase 06 outline suggested. The reason a *report* is needed at all is
  unchanged from the outline — a list filter cannot express "has no superseding record" — but the
  anti-join (collect every `supersedes` target, then exclude those names from the
  `needs_action = 1` rows) is four lines of `frappe.get_all` with no SQL string, which keeps
  [`rules/frappe-discipline.md`](../../rules/frappe-discipline.md)'s "no raw SQL that writes" (and
  the spirit of "no unexplained SQL" generally) clean and is directly unit-testable.
- **Consequences / why:** grepping for "who creates a Paymob Audit Entry" returns one function
  (`paymob.audit.record`), matching the single-write-path discipline used for Payment Entries. The
  immutability guarantee holds even against a compromised or careless server-side caller, because
  it is enforced by `docstatus`, not by remembering not to call `.save()` on a submitted doc.

---

### ADR-0012 — The audit writer moved to its own module

**Date:** 2026-07-27 · **Status:** Accepted

**Functional:** Nothing changes for anyone reading an audit entry; this is about where the code
that writes one lives.

**Technical:**
- **Context:** [ADR-0009](#adr-0009--audit-entries-are-submittable-and-immutable-a-resolution-is-an-append-via-supersedes)
  declares `processor._audit` the one function that creates `Paymob Audit Entry` rows. Phase 09's
  duplicate-payment guard needs to write one from `paymob.ledger` — which `processor.py` already
  imports (to call `post_payment`), so `ledger.py` importing back would be circular.
- **Decision:** Extract the function verbatim into `paymob.audit::record(txn, attempt, event,
  needs_action, description, actor, **amounts_fields)`, imported by both `processor.py` and
  `ledger.py`. `actor` becomes a required parameter instead of a hardcoded string — each of
  `processor.py`'s three call sites passes
  `"paymob_integration.paymob.processor.process_transaction"` explicitly (the same value it got
  implicitly before), and `ledger.py`'s call site passes
  `"paymob_integration.paymob.ledger.post_payment"`.
- **Consequences / why:** "one function creates audit entries" (ADR-0009) stays literally true
  across two call sites instead of becoming two functions with the same shape. Every future caller
  of `post_payment` — the Phase 10 poller, the Phase 11 refund path — inherits the duplicate-audit
  behaviour and the shared writer for free, instead of each having to remember to write one.
  Proven behaviour-preserving: `test_processor.py` passed unchanged before any new duplicate-guard
  code was added on top of the move.

### ADR-0013 — `process_transaction` runs as Administrator, and gets a manual rescue button

**Date:** 2026-07-27 · **Status:** Accepted

**Functional:** A Paymob Transaction stuck at "Processed: No" can be manually re-driven from its
Desk form with a **Process** button, visible to whoever can already read that doctype (System
Manager, Accounts Manager).

**Technical:**
- **Context:** [ADR-0006](#adr-0006--the-processed-callback-is-the-apps-only-allow_guesttrue-method)
  makes `webhooks.processed_callback` the app's only `allow_guest=True` method. `frappe.enqueue`
  inherits the calling request's user, so the job it schedules for `processor.process_transaction`
  starts as `Guest`. Live traffic confirmed the failure mode: ERPNext's `create_payment_entry` →
  `get_payment_reference_details` calls `frappe.has_permission(reference_doctype, "read", ...,
  throw=True)` on the Sales Invoice — a check no `ignore_permissions=True` on our own document
  saves can reach, because it fires inside ERPNext core, not our code. Guest has no such
  permission, the job raised `PermissionError`, and the transaction was left at `processed = 0`
  with the attempt stuck `Pending` forever — silently, since RQ marks the job failed and nothing
  polls for that failure yet (that's Phase 10).
- **Decision:** `process_transaction` sets `frappe.session.user = "Administrator"` for its
  duration (restored in a `finally`), regardless of who enqueued it. The data it acts on is
  already HMAC-verified server-to-server fact (ADR-0006), not a user-supplied request, so a
  privileged system actor is correct here the same way `ignore_permissions=True` already is on
  every write in this module. Separately, `paymob_transaction.process(name)` is a whitelisted
  rescue: it checks `frappe.get_doc("Paymob Transaction", name).check_permission("read")` — the
  DocType's own `permissions` list is the source of truth for who may press the button, not a
  hardcoded role list that could drift from `paymob_transaction.json` — then calls
  `processor.process_transaction`. It is not a retry of a Paymob API call (rules/payments.md still
  forbids auto-retrying capture/refund/void); it is a human re-running our own idempotent
  consumption of a row already durably stored, safe because `process_transaction` no-ops on
  `processed = 1`.
- **Consequences / why:** Every future background job enqueued from the guest webhook — the
  Phase 10 poller's write path, the Phase 11 refund/void consumer — needs the same privileged-actor
  treatment; this is the first, and the pattern (`set_user` in a `finally`) is now precedented.
  The button is a stopgap for exactly the gap Phase 10's poller is meant to close automatically;
  it does not replace that phase, it covers the interval until it exists.
