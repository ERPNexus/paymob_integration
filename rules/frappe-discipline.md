# Rule: Frappe Discipline

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (blocking at review)

## Why this rule exists

Frappe gives you several ways to change data, and the fastest ones skip the safety. Generated
code prefers the fast ones, because they never raise validation errors and never fail on a
document conflict. In a payment app, the checks being skipped are exactly the ones that keep
the ledger honest.

## The requirement

### Writing documents

- **No `db_set` on status, amount, or any money-related field.** It writes straight to the
  database column, skipping validation, hooks, and the version trail. Use the document API and
  let validation run.
- **No raw SQL that writes.** Reads with `frappe.db.sql` are acceptable when a query genuinely
  needs it; writes go through the ORM.
- **No `ignore_permissions=True`** on a money-moving path unless there is a comment naming the
  system actor and why a user's permission cannot apply. It is not a way to make an error go
  away.
- **No `ignore_validate` or flag-based bypasses** to make a Payment Entry submit.

### Documents that must not be edited

Submitted Payment Entries are immutable. A correction is a cancellation and a new entry, or an
opposite entry — never an edit of the original. This is the ledger's whole value.

### Schema and data changes

- DocType JSON is committed with the change, never created by hand on a site.
- Any change to existing data goes through a patch listed in `patches.txt`. Patches are
  idempotent — running twice must be safe.
- No destructive migration on money data. Do not drop or rewrite a field holding amounts or
  transaction identifiers without a decision entry in `docs/reference/decisions.md`.

### Where logic lives

- Document lifecycle logic belongs in controller hooks (`validate`, `on_submit`, `on_cancel`),
  not scattered in whitelisted methods.
- `hooks.py` entries stay explicit and readable.
- Long or external work runs in a background job, not inside a web request — except money
  operations that must complete inside their lock.

### Concurrency

- Read-then-write on a money field takes a row lock (`for_update=True`) or relies on a unique
  database constraint. An `if` statement is not a lock.

### Session and user switching

- **Never call bare `frappe.set_user` on a path reachable from an HTTP or web request.** It is
  safe in an enqueued RQ job, which has no live session to protect. Inside a request it stamps
  `session.sid` to the *username* and empties `session.data`, and restoring the original user
  with a second bare `set_user` call does the same damage again — the caller's session is
  corrupted and their next request logs them out (issue #8). Use
  `paymob.session.as_administrator()`, which saves and restores what `set_user` clobbers.

## Definition of Done

- [ ] No `db_set` on status or money fields in the change.
- [ ] No writing raw SQL, no unexplained `ignore_permissions`.
- [ ] Submitted ledger documents are corrected by cancel/new, never edited.
- [ ] DocType JSON committed; data changes have an idempotent patch.
- [ ] Lifecycle logic sits in controller hooks.
- [ ] No bare `frappe.set_user` on a request-reachable path; use `paymob.session.as_administrator()`.
- [ ] `pre-commit run --all-files` passes.

## What this rule is NOT

- Not a ban on `db_set` everywhere. It is acceptable for non-money bookkeeping fields such as a
  "last polled at" timestamp, where validation adds nothing.
- Not a style guide. Formatting and naming are in `AGENTS.md` and enforced by Ruff.
