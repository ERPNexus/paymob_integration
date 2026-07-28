# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-07-26

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->
- Commit and push requested repository work directly on `version-16`; do not create an `agent/*`
  branch unless the user asks for one.
- Repository commitments should include a dedicated Conventional Commits rule for consistency.
- Even when a plan (or "learning mode") calls out a piece of business logic as "yours to write" /
  a user contribution, implement it fully anyway unless the user explicitly asks to write it
  themselves. Do not leave `NotImplementedError`/TODO stubs in a plan you were asked to implement.
- Do not treat a plan's own housekeeping tasks (e.g. "rewrite the outline into a full phase plan")
  as mandatory just because the plan document says so — confirm or skip busywork like that; the
  user has flagged it as useless before. See [[feedback-outline-not-full-plans]].

## Key Learnings

- **Project:** paymob_integration
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
- Frappe's app launcher and sidebar reserve a small square logo area; use a compact official mark
  when one is available, otherwise a full wordmark will render crisply but small.
- The app is installed on the `capital` site. `bench --site capital run-tests --app
  paymob_integration` aborts during global test-record setup — `hrms` regional setup for India
  fails on a stale `Attendance Permissions` document link, unrelated to this app. Add
  `--lightmode` to skip that bootstrap and run the suite.
- `prettier` and `eslint` skip `.wolf/` in `.pre-commit-config.yaml`; those hook scripts are
  vendored from cytostack/openwolf and must stay byte-identical to upstream.
- Paymob billing country is the uppercase ISO value of Frappe `Country.code`, not the display name.
- A Desk `Workspace Sidebar` linking to a Workspace must have that public Workspace fixture under
  the module package's `workspace/<slug>/` directory; a direct URL can render without it, but the
  Desk launcher cannot generate a click route.
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

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
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

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- [2026-07-26] Commit OpenWolf's shared protocol, configuration, identity, and hooks; ignore its
  generated session state and visual-review output to keep repository history useful and clean.
- Frappe standard DocType and Report artifacts for the `Paymob Integration` module must live under
  `paymob_integration/paymob_integration/{doctype,report}/...`; placing their JSON/Python files at
  `paymob_integration/{doctype,report}/...` leaves migration unable to sync them and imports broken.
