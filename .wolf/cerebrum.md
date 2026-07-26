# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-07-26

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->
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

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->
- [2026-07-26] Commit OpenWolf's shared protocol, configuration, identity, and hooks; ignore its
  generated session state and visual-review output to keep repository history useful and clean.
