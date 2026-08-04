# Implementation Plans

Thirteen numbered phases that build the Paymob ↔ ERPNext integration. Each phase is one
**slice** as defined by [`../rules/slices.md`](../rules/slices.md): one vertical piece of
working behaviour, small enough to review in one sitting, shipping code + schema +
permissions + tests + docs + translations in the same change.

They are ordered by the payment's own lifecycle, not by code layer. Phase N assumes every
phase before it is merged.

## Why plans live here and not in `docs/`

`docs/` is the published product documentation — a merchant or an integrating developer reads
it. Plans are internal build instructions with a finite life. Neither fits, so plans get their
own top-level folder.

## The phases

| # | Phase | Ships this observable behaviour |
|---|---|---|
| [01](01-settings-and-credentials.md) | Settings & credentials | A merchant saves Paymob keys and clicks **Test Connection**; the site proves it can authenticate against Paymob |
| [02](02-create-intention-and-checkout.md) | Intention & checkout URL | A user opens a submitted Payment Request, clicks **Pay with Paymob**, and gets a working hosted-checkout URL |
| [03](03-result-page.md) | Customer result page | The customer's browser lands on `/paymob-result` and sees a status page driven by local state, never by URL parameters |
| [04](04-webhook-hmac-verification.md) | Webhook & HMAC verification | A forged callback is refused; an authentic one is acknowledged |
| [05](05-transaction-record-and-dedup.md) | Transaction record & dedup | An authentic callback is stored once; the same delivery twice stores nothing extra and still returns 200 |
| [06](06-state-machine-and-audit.md) | State machine & audit trail | A verified success moves the attempt to `paid`; an illegal transition is refused and audited |
| [07](07-amount-verification.md) | Amount verification | An authentic callback whose amount differs from the snapshot is held for a human, not posted |
| [08](08-ledger-write-path.md) | The single ledger write path | A verified, amount-matched success creates one submitted Payment Entry allocated to the Sales Invoice |
| [09](09-duplicate-payment-guard.md) | Duplicate payment guard | A second genuine payment for one Payment Request posts nothing and raises a refund flag |
| [10](10-reconciliation-poller.md) | Reconciliation & expiry | A lost webhook is recovered by Transaction Inquiry; an abandoned checkout becomes `expired` |
| [11](11-refund.md) | Refund | Staff refund from ERPNext under a server-side lock; the reversing entry is posted from the verified callback |
| [12](12-pre-go-live-verification.md) | Pre-go-live verification | Immediate-capture integration IDs and the verified payment lifecycle are measured before real money moves |

## Dependency order

```
01 ─┬─ 02 ─┬─ 03
    │      └─ 04 ── 05 ── 06 ── 07 ── 08 ─┬─ 09
    │                                     ├─ 10
    │                                     └─ 11
    └────────────────────────────────────────────── 12 (last, needs everything)
```

Phases 09, 10 and 11 are independent of one another and may be built in any order once 08 is
merged.

## Global constraints

Every task in every phase inherits these. They are the enforceable form of
[`../rules/implementation-gate.md`](../rules/implementation-gate.md).

**Money** (from [`../rules/payments.md`](../rules/payments.md))

- Exactly **one** function creates Payment Entries. Grep answer for "who inserts a Payment
  Entry" must stay at one.
- A Payment Entry is never created from the HTTP response of a Paymob call — only from a
  verified webhook or a Transaction Inquiry result.
- Payment Request status is **derived** from submitted Payment Entries. Never `db_set`.
- Every Payment Entry is allocated to the specific Sales Invoice through `references`.
- HMAC-SHA512 verification runs **before** any document load, amount read, or database access.
  Comparison uses `hmac.compare_digest`, never `==`.
- Authenticity, success state, and amount match are three separate checks. All three pass or
  nothing posts.
- Money is **integer cents**. No float arithmetic, no float equality.
- Incoming duplicates are stopped by a **unique database constraint**, not an `if`.
- Outgoing refund calls take a **server-side lock before** the request.
- Reads may be retried automatically. Refunds may **never** be retried
  automatically — Paymob takes no idempotency key.
- A 401, timeout or 5xx never changes payment state. Auth-token expiry ≠ intention expiry.
- A decline updates status only: no ledger row, no change to the Sales Invoice, and a new
  attempt must still be possible.
- Every `@frappe.whitelist()` method that moves money checks permission on the document first.
  Browser-supplied amounts and references are never authoritative.
- Every outbound call sets a `timeout` and handles connection errors explicitly.

**Frappe** (from [`../rules/frappe-discipline.md`](../rules/frappe-discipline.md))

- No `db_set` on status, amount, or any money field. Non-money bookkeeping fields such as
  `last_polled_at` are the documented exception.
- No writing raw SQL. No unexplained `ignore_permissions=True`.
- Submitted Payment Entries are corrected by cancel + new, never edited.
- DocType JSON is committed with the change; data changes go through an idempotent patch in
  `patches.txt`.
- Read-then-write on a money field takes a row lock (`for_update=True`) or relies on a unique
  constraint.

**Secrets** ([`../rules/secrets.md`](../rules/secrets.md))

- Credentials use the **Password** fieldtype and `get_password()`. Never `Data`.
- Test fixtures use obviously fake values (`sk_test_FAKE_...`).
- Only the **public key** and the per-session **client secret** may reach the browser.
- Never log a credential, card data, or a full webhook payload.

**Errors** ([`../rules/error-handling.md`](../rules/error-handling.md))

- No bare `except`, no `except Exception: pass`. Every handler logs a named error, re-raises,
  or sets an explicit state a human or the poller will act on.
- Catch the specific exception. Never wrap a whole function body in one `try`.
- Webhook status codes: verification failure → error status with no explanation; already
  processed → 200; internal failure while persisting an authentic message → non-2xx.

**Logging** ([`../rules/logging.md`](../rules/logging.md))

- Every payment log line carries the **Payment Request name**. Use `frappe.logger("paymob")`.
- One line per stage. Log lines are English and are not translated.

**Translation** ([`../rules/translation.md`](../rules/translation.md))

- Every user-facing string is wrapped in `_()` / `__()` / `{{ _() }}`.
- Never assemble a sentence from concatenated translated fragments.
- All Arabic lives in `paymob_integration/translations/ar.csv` and nowhere else.
- Fieldnames, DocType names, and stored Select values stay English.

**Testing** ([`../rules/testing.md`](../rules/testing.md))

- **No test makes a network call.** Ever. `requests.request` is patched.
- Money assertions count Payment Entry rows and check allocations. "It did not raise" proves
  nothing.

**Style** (from `AGENTS.md`)

- Tabs for indentation. Double quotes. Python 3.14 target. Ruff rules from `pyproject.toml`.
- DocType JSON: one-space indentation, no final newline (written by Frappe, do not reformat).
- `pre-commit run --all-files` passes before every commit.

## Design decisions this plan makes

These were not settled by `docs/` and were decided while writing the plan. Each becomes an ADR
in `docs/reference/decisions.md` in the phase that introduces it. **Review these first — if one
is wrong, the phases built on it are wrong.**

1. **A `Paymob Payment Attempt` doctype owns the lifecycle state, not the Payment Request.**
   `docs/reference/states.md` says a retry is a *new* attempt with a new special reference, and
   that `failed` is terminal *for that attempt*. Fields on the Payment Request cannot express
   "this Payment Request has one failed attempt and one pending attempt". (Phase 02, ADR-0004)

2. **Dedup uses a unique `event_key = "<transaction_id>:<event_kind>"` column.** MariaDB gives
   us a single-column unique index for free through Frappe's `unique` property; a composite
   unique on two fields would need a hand-written patch. The key is computed in `validate`, so
   the constraint is in the database, not in an `if`. (Phase 05, ADR-0005)

3. **The webhook endpoint is the one `allow_guest=True` method in the app.** Paymob's servers
   have no Frappe session. Its authentication is the HMAC, checked before anything else, and it
   performs no work under a caller's identity — it verifies, persists, enqueues, and returns.
   `rules/payments.md` rule 17 calls `allow_guest` on a money-moving method an automatic reject;
   this is the documented exception, and it is the *only* one. (Phase 04, ADR-0006)

4. **An authentic message is durably accepted before it is processed.** The endpoint returns 200
   once the `Paymob Transaction` row is committed. Failures *after* that point are retried by our
   own job and by the poller, not by Paymob — because Paymob's retry behaviour is undocumented and
   must be assumed to be zero. A non-2xx is returned only when persistence itself fails.
   (Phase 05, ADR-0007)

5. **The single write path delegates to ERPNext's own `PaymentRequest.create_payment_entry`.**
   It already builds an allocated, submitted Payment Entry and links the reference rows back to
   the Payment Request, which is what makes the status derive correctly. Hand-building a Payment
   Entry would re-implement that and get the allocation wrong. The clearing account is supplied
   by setting `payment_account` on the **in-memory** Payment Request document before the call —
   never saved, so no `db_set` on a submitted document. (Phase 08, ADR-0008)

6. **Audit entries are submittable and immutable; a resolution is a new record that supersedes
   the old one.** `rules/audit-trail.md` forbids editing an audit record but also requires a
   place to record that a human acted. Those only coexist if resolution is an append. The
   "needs action" view is a committed Query Report, because a list-view filter cannot express
   "has no superseding record". (Phase 06, ADR-0009)

7. **The `payments` app is not a dependency.** It is not installed on this bench, and
   `Payment Gateway` (the doctype its controller pattern needs) does not exist here. The
   integration drives the Payment Request directly. (Phase 02, ADR-0010)

## Depth of each file

Phases **01 and 02 are written out in full** — every file, every test, every command, in
task-by-task form. They double as the worked example of what a phase plan looks like here.

Phases **03–12 are outlines**: goal, scope, and the list of things that must be true. Expand one
into a full plan (using 01 as the shape) immediately before building it, not before. Writing all
twelve in advance would mean planning Phase 11 against assumptions Phase 05 has not tested yet.

## How to execute a phase

1. Read the whole phase file before writing any code.
2. Work the checkboxes in order. Each is one action, two to five minutes.
3. Run the test after writing it and **watch it fail** before implementing. A test that has
   never failed has never been tested.
4. Commit at the marked points, with the Conventional Commit message given.
5. At the end of the phase, walk the Definition of Done. A phase with an unticked box is not
   merged — it is split.

## Review checklist for a finished phase

Run [`../rules/implementation-gate.md`](../rules/implementation-gate.md)
item by item against the diff. The phase's own Definition of Done covers what that phase
touches; the gate covers what it might have broken.
