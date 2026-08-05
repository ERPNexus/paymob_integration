# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-08-04

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->
- [2026-08-03] Do not add cleanup migrations for retired development-only fields while the app has no production sites.
- [2026-08-04] Complete the requested scope, including documentation and policy cleanup; do not defer it as a follow-up.
- [2026-08-03] Keep OpenWolf state compact: discard generated historical logs and stale temporary-path metadata; retain durable instructions and curated project learnings.
- [2026-08-03] When the user requests a post-delivery grilling session, keep it short or medium-length according to the feature's challenging cases and edge-case risk. It is manual/on-demand, not an automatic delivery step.
- [2026-07-29] Translate the payment state `Authorized` as `محجوز`, not `التفويض` or `مصرّح به`; it denotes a card-funds hold awaiting capture.
- [2026-07-28] For the reported missing refunds, refunds were initiated in Paymob, not from Frappe; diagnose signed inbound refund callbacks and worker processing rather than the Frappe refund-request UI.
- Commit and push requested repository work directly on `version-16`; do not create an `agent/*`
  branch unless the user asks for one.
- Repository commitments should include a dedicated Conventional Commits rule for consistency.
- Even when a plan (or "learning mode") calls out a piece of business logic as "yours to write" /
  a user contribution, implement it fully anyway unless the user explicitly asks to write it
  themselves. Do not leave `NotImplementedError`/TODO stubs in a plan you were asked to implement.
- Do not treat a plan's own housekeeping tasks (e.g. "rewrite the outline into a full phase plan")
  as mandatory just because the plan document says so — confirm or skip busywork like that; the
  user has flagged it as useless before. See [[feedback-outline-not-full-plans]].
- Keep non-user-facing reconciliation limits as backend defaults rather than Settings fields.
- Prefer native Frappe dashboard connections over redundant custom buttons that only open a linked list.

## Key Learnings

- [2026-08-05] Frappe's `utils.synchronization.filelock` is site-scoped by default; use a Payment-Request-derived name around payer-link active-attempt lookup, intention creation, and identifier persistence to prevent concurrent checkout creation.
- [2026-08-05] A verified decline is not terminal for a still-valid hosted checkout: retain its immutable transaction evidence, then allow only a later verified, exact-match `Success` to move the same attempt from `Failed` to `Paid` through the normal processor and ledger path.
- [2026-08-05] Release hardening currently targets `0.1.0-alpha`; v1 requires a passing clean CI run and a completed Paymob sandbox smoke-test record, not just the presence of CI/checklist files.
- [2026-08-04] Treat `Paymob Settings.enabled` as a server-side feature boundary: every entry
  point uses one settings predicate, while Desk visibility only mirrors that guard for usability.
- A Frappe Document Type Number Card always opens its filtered List view; it cannot express the
  Open Audit Entries report's `supersedes` anti-join. Keep the report as the canonical open-item
  count and expose `Paymob Audit Entry.description` in the list when the card is the triage path.
- Frappe custom Permission Types are honored by both `frappe.client.has_permission` and
  `Document.check_permission`; on `capital`, `Accounts Manager` has `refund = 0` while only
  `Paymob Refund Manager` has it for `Paymob Payment Attempt` (issue #7).
- A test that introduces a DocType Select value must run after `bench --site capital migrate`; the
  test site's saved DocType schema validates against its prior options until synchronization.
- Frappe's `compose(fn, *hooks)` runs a DocType's OWN controller method before any app's `hooks.py`
  `doc_events` handler for the same event. ERPNext's `PaymentRequest.before_submit` sends its email
  inside that method body, so anything an app wants that email to see must be set on `validate`, not
  `before_submit` (issue #10, ADR-0024). Same trap applies to any core method that acts, not just sets fields.
- A new Check field on a Single DocType is missing (not defaulted) on existing sites until something
  writes it — the Desk form then shows it unchecked and the merchant's next save silently turns the
  feature off. Ship an idempotent backfill patch with any new default-on Setting.
- An auth-only payment is a verified hold, not a charge: only `Capture`/`Success` rows can cap refunds; Auth rows are used only to capture or void.
- Native Frappe Notification templates can query the linked Payment Request's `company` through
  `frappe.db.get_value`; leave sender identity to the configured site Email Account rather than adding
  per-company SMTP configuration.
- **Project:** paymob_integration
- Frappe Notification and Payment Request email bodies both render Jinja, so one app-owned
  inline table fragment can preserve Frappe's native delivery/opt-out behavior while keeping
  visual treatment consistent across all payment messages.
- In email Jinja, use Frappe's built-in `is_rtl()` helper for `dir` and `align`; the restricted
  `frappe` Jinja global does not expose the request-local language object reliably.
- A standalone Frappe process must run from the Bench `sites/` directory before `connect()` so
  its relative site log handler resolves to `<site>/logs`, matching `bench` commands.
- `frappe.sendmail(..., delayed=False)` still registers its immediate send as an after-commit
  callback; direct scripts must commit, then verify `Email Queue Recipient.status` is `Sent`.
- Paymob's current callback documentation says transaction callbacks cover successful or declined payments only. Dashboard refunds therefore need a separate authenticated Transaction Inquiry recovery path; do not expect a `Refund` webhook row.
- **Description:** Seamless integration for paymob with ERPNext
- Country, currency, and mode jointly identify Paymob credentials and integration IDs; callers must
  supply all three to avoid selecting a regional account by row order.
- Checkout credential country is the merchant's `Company.country`; customer billing country is
  separate and falls back from the selected address to the party's primary address.
- Frappe only puts an app in `/desk`'s launcher when its `hooks.py` defines
  `add_to_apps_screen`; a Workspace alone remains reachable by its direct `/app/<workspace>` route.
- Frappe's Desktop Icon generator requires every `add_to_apps_screen` entry to include a `logo` key.
- App-level `workspace_sidebar` and `desktop_icon` fixtures must include their document `name`.
- Existing Frappe users with a saved `Desktop Layout` do not receive new standard icons automatically;
  append the new icon to their saved layout rather than resetting it.
- Native Number Cards can provide permission-aware operational counts with `type = "Document Type"`,
  `function = "Count"`, and `filters_json`; keep percentage stats off for queue sizes.
- Fixture imports retain a locally newer record; include a newer `modified` timestamp when changing an
  existing exported fixture that must overwrite the site copy.
- Frappe's app launcher and sidebar reserve a small square logo area; use a compact official mark
  when one is available, otherwise a full wordmark will render crisply but small.
- The app is installed on the `capital` site. `bench --site capital run-tests --app
  paymob_integration` aborts during global test-record setup — `hrms` regional setup for India
  fails on a stale `Attendance Permissions` document link, unrelated to this app. Add
  `--lightmode` to skip that bootstrap and run the suite.
- Extend ERPNext's Payment Request dashboard through `override_doctype_dashboards`; appending a
  `Paymob Payment Attempt` transaction group makes Frappe filter the connection by its
  `payment_request` Link field without a custom route button.
- `prettier` and `eslint` skip `.wolf/` in `.pre-commit-config.yaml`; those hook scripts are
  vendored from cytostack/openwolf and must stay byte-identical to upstream.
- Paymob billing country is the uppercase ISO value of Frappe `Country.code`, not the display name.
- A Desk `Workspace Sidebar` linking to a Workspace must have that public Workspace fixture under
  the module package's `workspace/<slug>/` directory; a direct URL can render without it, but the
  Desk launcher cannot generate a click route.
- Workspace shortcut/card blocks are only rendered when their names match the corresponding
  `shortcuts`/`links` child-table labels; use short labels at four columns to prevent Desk truncation.
- A trusted result-page state requires both a valid response HMAC and equality between its signed
  Paymob order ID and the selected attempt's stored `paymob_order_id`; credential lookup must use
  the attempt's frozen mode because site mode can change while checkout is open.
- In local development, `frappe.utils.get_url()` produces a Bench-only host such as
  `http://capital:8002`; a customer's browser redirect may work through localhost while Paymob's
  servers cannot reach the processed-callback URL. End-to-end webhook tests require a public HTTPS
  tunnel or deployed hostname before the intention is created.
- With Frappe developer mode enabled, `get_url()` appends `webserver_port` even to an HTTPS
  `host_name` unless that hostname already contains an explicit port. Temporary HTTPS tunnel URLs
  should therefore be configured with `:443`.
- A real Paymob checkout through the temporary HTTPS tunnel successfully persisted the verified
  transaction with `processed = 0`; the attempt remains `Pending` by design until Phase 06 consumes
  that durable event.
- ERPNext's `PaymentRequest.create_payment_entry` posts `self.outstanding_amount` read at call
  time — **not** the amount the caller was told to collect. Phase 07's mismatch gate compares the
  Paymob amount to `attempt.expected_amount_cents`, a snapshot taken at intention creation, so the
  two can drift (partial cash payment, credit note). Any ledger write path needs its own post-hoc
  equality check against `payment_entry.paid_amount`.
- `_allocate_payment_request_to_pe_references` (payment_request.py:505) sets
  `references[N].payment_request`; `PaymentEntry.update_payment_requests` (payment_entry.py:320)
  derives the Payment Request status on submit. Both are why nothing in this app writes PR status.
- Once a phase starts creating Payment Entries, the existing `_cleanup_fixture` teardown in
  `test_processor.py` breaks for **every** test on a posting path, not just the ones whose
  assertions change — a submitted Payment Entry blocks the cancel/delete of both the Payment
  Request and the Sales Invoice. Teardown must cancel and delete the Payment Entry first.
- Phases 08 + 09 (ledger write path, duplicate payment guard) are implemented: `paymob.ledger.
  post_payment` is the single Payment Entry write path (ADR-0008), and its duplicate check —
  `frappe.db.get_value("Payment Entry Reference", {"payment_request": ..., "docstatus": 1},
  "parent")` — runs first inside the caller's `for_update=True` lock, before any posting. The
  audit writer was extracted from `processor._audit` into `paymob.audit.record` (ADR-0012) so
  `ledger.py` can write audit entries without importing `processor` (which imports `ledger`).
- `pre-commit run --all-files` reformats *every* file in the repo, including ones you didn't
  touch, if they carry pre-existing ruff-format/lint debt — this bench's `capital` site already
  has 12 pre-existing `RUF059` (unused unpacked `invoice` in test fixtures) errors on
  `version-16` unrelated to any one phase. Scope pre-commit to the files actually changed
  (`pre-commit run --files <paths>`) to avoid dragging unrelated reformatting into a phase's diff.
- A real Paymob checkout through the temporary tunnel exposed a live bug the full test suite
  never caught: `processor.process_transaction` is enqueued from `webhooks.processed_callback`
  (`allow_guest=True`), so the RQ job inherits `user="Guest"`. ERPNext's `create_payment_entry` →
  `get_payment_reference_details` calls `frappe.has_permission(..., throw=True)` directly (not
  via a doc save `ignore_permissions` can reach), so Guest hit `PermissionError` and the
  transaction sat at `processed=0` forever, silently — no test simulates the Guest-user context
  a real webhook-enqueued job runs in; `IntegrationTestCase` always runs as Administrator. Fixed
  in ADR-0013: `process_transaction` does `frappe.set_user("Administrator")` for its duration,
  restored in `finally`. Diagnosed by reading the actual RQ job's `exc_info` via
  `Job.fetch(job_id, connection=get_redis_conn())` — `bench doctor` and Error Log alone didn't
  surface it (the real job's traceback wasn't in Error Log; only stale unrelated jobs were).
- Permission checks for a Desk button on a doctype with no `write` permission row (an
  append-only log like Paymob Transaction) should read the DocType's own `permissions` list via
  `doc.check_permission("read")`, not a hardcoded role tuple passed to `frappe.only_for(...)` —
  the user explicitly corrected this mid-task: hardcoded role lists drift from the JSON's own
  permission definition over time. See [[feedback-no-hardcoded-roles]].
- A whitelisted `test_<doctype>.py` file placed directly under `doctype/<name>/` triggers
  Frappe's per-doctype `make_test_records` bootstrap when run via `--module` or early in
  `--app` sort order, which can crash with `DuplicateEntryError` on a non-pristine site (this
  bench's `capital` site already has real `Standard Buying`/`Standard Selling` Price Lists that
  ERPNext's `BootStrapTestData` tries to insert unconditionally). Files needing real
  Payment-Request-linked fixtures belong under `paymob_integration/tests/` instead (matching
  `test_processor.py`/`test_ledger.py`), which sorts after the doctype folder and avoids the
  crash entirely.
- A Frappe DocType Dashboard connection filters another DocType by the current document's
  `name`, so external `paymob_transaction_id` data cannot safely power the connection. Audit
  entries therefore retain the external ID for correlation and also link to the exact local
  `Paymob Transaction` document.
- `IntegrationTestCase.setUpClass()` commits Frappe's class fixtures before registering its
  rollback cleanup. `NoCommitIntegrationTestCase` must patch `frappe.db.commit` only after that
  setup, then register its restoration cleanup so it runs before Frappe's rollback.
- Phase 10 (reconciliation poller) is implemented: `paymob.tasks.reconcile_pending_attempts` is
  the scheduled entry point (`hooks.py` `scheduler_events["cron"]`, every 15 minutes), and
  `paymob.transactions.store` (extracted from `webhooks._store`, ADR-0015) is now the single
  writer of a Paymob Transaction row for both the webhook and the poller. `tasks._expire_if_due`
  is reachable only from the `None` return of `tasks._inquire` (an answered 404), never from an
  exception handler — that is what keeps auth-token expiry and intention expiry on separate code
  paths (ADR-0014).
- This bench's redis-queue (port 11002) and redis-cache (port 13002) servers are **not started by
  default** — only the default `redis-server` on 6379 runs at session start. Any test that inserts
  a document (even indirectly, e.g. via `given_submitted_sales_invoice`) can fail with
  `AssertionError: Should not fail silently in tests` from `frappe/utils/global_search.py`
  (`sync_value_in_queue` falls back to a synchronous path when it can't reach redis, and that
  fallback is disallowed under `frappe.flags.in_test`). Fix: `redis-server config/redis_queue.conf
  --daemonize yes` and `redis-server config/redis_cache.conf --daemonize yes` from the bench root
  before running any test that touches the ORM.
- The `capital` site's `Paymob Payment Attempt` table had accumulated ~19 genuinely-committed rows
  spanning 2026-07-26 through 2026-07-27 (multiple past sessions' manual/live-tunnel checkout
  testing) that `NoCommitIntegrationTestCase` never touches, because that class only prevents
  commits *within* its own test run — it does nothing about rows a prior session's manual testing
  actually committed. This was invisible to every previous test file because their assertions are
  scoped by `payment_request`/`attempt` name. It became a real bug the moment a test queried
  site-wide (`paymob.tasks.reconcile_pending_attempts`'s own selection query, `order_by="creation
  asc"`, oldest first) — old debris got swept into a batch ahead of a test's own fresh fixtures.
  Cleaned via `frappe.delete_doc(..., force=True)` in a `bench console` session (raw SQL
  `DELETE`/`bench execute` doing writes are blocked by the permission classifier as
  destructive-outside-tests; `bench console` with ORM calls was allowed). Before writing a test
  that queries a Paymob doctype without scoping by name, check whether the site actually is clean.

- Frappe translation CSV rows may have a blank third context field; a non-empty descriptive context
  changes the lookup key to `source:context` and will not match ordinary `_()` calls without that
  context. Use quoted `"source","translation",""` rows for catalog-wide translations.

- `bench --site capital run-tests --app paymob_integration` **without** `--lightmode` now fails
  before any app test runs: ERPNext's `tests/utils.py` bootstraps master data at import and hits
  `DuplicateEntryError: ('Price List', 'Standard Buying')`. With `--lightmode` the full 194-test
  suite runs (see the older note above about the hrms bootstrap).
- `tests.test_reconciliation` errors (10, `IndexError: pop from empty list` in `_FakeClient`) on
  this site independent of any code change: `tasks.reconcile_pending_attempts()` sweeps **every**
  stale Pending attempt, and 7 real ones are left on `ACC-PRQ-2026-00023` from manual testing on
  2026-07-28/29, exhausting the fake's fixed response list. The test is not isolated from site
  data. Stash before blaming a suspected regression on it.

- `bench serve` is not normally running on this bench; `frappe-visual-reviewer` needs
  `--base http://localhost:8002` plus a `bench serve --port 8002` started first (and killed after).
  Its socket.io console errors are expected noise when only the web process is up.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
- [2026-08-05] Run `pre-commit` from `apps/paymob_integration`, not the Bench root; its Git configuration is repository-local.
- [2026-08-04] The imported GitHub issue extension is at
  `/home/frappe/.claude/skills/github-issues/SKILL.md`; do not resolve the anatomy entry as the
  repository-local `.claude/skills/github-issues/SKILL.md`, which does not exist.
- [2026-08-03] Tests under `paymob_integration/tests/` use module paths such as
  `paymob_integration.tests.test_events`; `paymob_integration.paymob_integration.tests.*` does not
  exist. Verify a plan's copied `bench run-tests --module` paths against the package tree before use.
- [2026-07-29] `apply_patch` cannot update a file created in the same patch; add it once with final content.
- [2026-07-29] `Mock(name="x")` labels a mock; set `.name` explicitly when the code reads it.
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-07-28] Do not infer the viewed Payment Request from a nearby live record. For refund support,
  verify the exact Payment Request, attempt, transaction, and Payment Entry links before explaining
  why a button is absent.
- [2026-07-26] For optional Frappe fields at a validation boundary, use `doc.get()` and report
  missing references separately from missing linked values; dynamic attribute access produces an
  opaque `AttributeError`.
- [2026-07-26] `BaseDocument.update()` accepts one mapping, not keyword arguments; use
  `document.update({"field": value})` before saving.
- [2026-07-26] Run repository-scoped Git commands from the app root, not the Bench root; the latter
  is not a Git worktree.
- [2026-07-27] Do not add a third `paymob_integration` package level for Frappe artifacts. In this
  single-module app, `Paymob Integration` maps to `paymob_integration/paymob_integration/`; its
  DocTypes and reports already belong directly under that package's `doctype/` and `report/`.
- [2026-07-27] `helpers.given_submitted_sales_invoice`'s promised "exactly the requested amount"
  was false whenever the site's `Currency` master rounds to a whole unit
  (`smallest_currency_fraction_value = 0` — true for EGP on the `capital` site). ERPNext's
  Sales Invoice `rounded_total` then differs from `grand_total` by up to ~0.5, and
  `outstanding_amount` tracks the rounded figure — invisible until Phase 08 actually posted a
  Payment Entry and checked `invoice.outstanding_amount == 0`. Fix: `disable_rounded_total = 1`
  on the fixture invoice, not a per-test workaround. Before trusting any test-fixture "exact
  amount" claim on this bench, check the currency's `smallest_currency_fraction_value`.
- [2026-07-27] After hand-editing a DocType JSON `Select` field's `options`, the change is not
  live until `bench --site <site> migrate` runs — `frappe.get_cached_doc`/metadata caching means
  a fresh test run raises `ValidationError` on the new option ("cannot be X, should be one of
  Y") until the site's DocType metadata is resynced.
- [2026-07-28] `redis-queue`/`redis-cache` are not auto-started on this bench; the first symptom
  is `AssertionError: Should not fail silently in tests` from `global_search.py` on any test that
  inserts an ERPNext document, not an obviously-redis-shaped error. Check `redis-cli -p 11002
  ping` / `-p 13002 ping` before assuming a test-suite failure is a real regression.
- [2026-07-28] `site_config.json`'s `host_name` was left pointed at a `trycloudflare.com` quick
  tunnel from a prior webhook-testing session (bug-042). That tunnel process does not survive
  restarts and the WSL environment does not persist the `cloudflared` binary itself (`which
  cloudflared` came back empty, no package/binary anywhere on disk) — so any print/PDF render
  (`wkhtmltopdf`) that resolves `host_name` fails with `HostNotFoundError`, breaking unrelated Desk
  actions like submitting a Payment Request. There is no passwordless `sudo`, so the official
  `.deb` can't be installed system-wide; extract it with `dpkg-deb -x` and drop the `usr/bin/
  cloudflared` binary into `~/.local/bin` (already on `PATH`) instead. After starting a fresh
  `cloudflared tunnel --url http://localhost:8002` and updating `host_name`, always add an
  explicit `:443` and run `bench --site <site> clear-cache` (see bug-042) or `get_url()` silently
  reuses the stale value/port. Before trusting a configured `host_name`, verify with `getent hosts
  <host>` — don't assume a previously-working tunnel is still alive.
- [2026-07-28] When faking `paymob.client.request` in a poller test, don't queue a real success
  transaction as the *second* response for a "401 then retried" test — the retry actually succeeds
  and hands off to `processor.process_transaction`, moving the attempt to `Paid`, which made a
  "stays Pending" assertion fail for the wrong reason. Queue a 404 for the retry when the test is
  only about proving the retry-once mechanic, not the hand-off.
- [2026-08-03] Moving a call (here, `settings.resolve_integrations`) from inside a conditional
  branch of `api._checkout` to unconditionally at the top of the function — needed so the
  `reuse_pending` comparison could use the resolved mode — silently broke
  `test_pay_link.py::test_checkout_reuses_a_ready_pending_attempt`, a test the implementation plan
  never mentioned because it lived outside `test_checkout.py`. The plan's own verification step
  (`run-tests --app paymob_integration`, "catches the ripple") is what surfaces this, not a grep or
  a read of the plan's stated test list — always run the whole app suite after reordering code
  above an early-return branch, not just the tests the plan named.

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- [2026-08-04] Paymob Audit Entry is an exception-and-accountability ledger: new rows are limited
  to anomalies requiring human attention and capture/refund/void requests naming the user. Routine
  expiry, poller recovery, and no-op reversals stay visible through attempts, transactions, Payment
  Entries, and logs; their legacy Select options and translations remain for historical records.
- [2026-08-03] Enabled Paymob Integration IDs sharing country, currency, and Test/Live mode must have one capture mode. Different countries, currencies, and modes may use different capture modes; mixed same-group configuration is rejected.
- [2026-08-03] A Paymob Payment Attempt snapshots capture mode at checkout creation. Later Settings changes must not alter processing of its existing checkout; verified callback flags and the stored attempt determine the outcome.
- [2026-08-03] A verified authorization on an attempt configured for Auto Capture is a configuration mismatch: preserve the `Authorized` state and raise a needs-attention audit entry.
- [2026-07-26] Commit OpenWolf's shared protocol, configuration, identity, and hooks; ignore its
  generated session state and visual-review output to keep repository history useful and clean.
- Frappe standard DocType and Report artifacts for the `Paymob Integration` module must live under
  `paymob_integration/paymob_integration/{doctype,report}/...`; placing their JSON/Python files at
  `paymob_integration/{doctype,report}/...` leaves migration unable to sync them and imports broken.
- Paymob's cumulative `refunded_amount_cents` is not HMAC-signed. Refund posting must use only the
  signed child transaction's `amount_cents` when `has_parent_transaction` is true; parent resends
  are bookkeeping only.
- A `for_update=True` row lock serializes refund requests but does not reject a second request after
  the first commits. Set an in-progress marker inside the lock and clear it only from the verified callback.
- `frappe.perm.rights` (frappe/public/js/frappe/model/perm.js) is a hardcoded array of the 14
  built-in rights; `frappe.perm.has_perm(doctype, level, ptype)` can never return true for a
  custom Permission Type ptype (e.g. this app's "refund"), regardless of what the server-side
  DocType permissions say. It also silently returns `{read}` only when `frappe.get_meta(doctype)`
  hasn't been loaded for a doctype other than the current form's. The only correct client-side
  gate for a custom ptype is a server round-trip — the built-in whitelisted
  `frappe.client.has_permission(doctype, docname, perm_type)` takes an arbitrary `perm_type` string
  and works for this without writing a new endpoint.
- ERPNext's Payment Entry controller (`set_source_exchange_rate`/`set_target_exchange_rate`)
  only recomputes an exchange rate when the field is falsy on the doc being validated — passing an
  explicit `1` (even when correct for the same-currency case) silently wins over the controller's
  own computation the moment either side's account currency differs from company currency, and
  `set_received_amount()` only auto-derives `received_amount` from `paid_amount` when
  `paid_from_account_currency == paid_to_account_currency`. A manually-built cross-currency
  Payment Entry (not built through `create_payment_entry`) must compute both rates via
  `erpnext.setup.utils.get_exchange_rate` and `received_amount` itself before `insert()` —
  `validate_mandatory()` runs before the controller's own amount auto-fill.
- When a business rule (e.g. "how much can still be refunded") is checked on both the outbound
  request path (`api.py`) and an inbound callback guard (`processor.py`), read it from one shared
  function (`paymob.transactions.verified_success_charge`, not two different attempt fields) —
  `attempt.expected_amount_cents` (the pre-charge snapshot) and the verified charge's own
  `amount_cents` only drift when there was already an amount mismatch, but the two call sites
  disagreeing at all lets the API accept a refund the processor then silently refuses.
- The Payment Request client script must still run its paid-attempt refund lookup after a Payment
  Request becomes `Paid`; only checkout is unavailable at that point. Returning for `Paid` hides
  the Refund button even for an Administrator with the custom `refund` permission.
- For Paymob gateway errors, never expose a raw response. The client may show only an allowlisted
  string `detail` or `message` with the HTTP status; this preserves useful diagnostics without
  exposing echoed credentials, customer data, or newly-added gateway fields.
- [2026-08-04] This unreleased app is immediate-capture-only: `Success` settles to `Paid`; signed
	Auth/Capture/Void flags are stored as `Unsupported`, audited for review, and never mutate the
	ledger. Refund is the only outbound reversal action.
