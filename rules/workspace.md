# Rule: Workspace Visibility

**Status:** Active · **Since:** 2026-07-26 · **Enforcement:** Convention (Definition of Done)

## Why this rule exists

A DocType, Report, or Page that only exists in the database is invisible to the people who
have to use it — a merchant checking a failed payment, a developer reconciling a webhook, a
reviewer verifying a slice actually shipped something reachable. Frappe does not add new
DocTypes to a workspace automatically; they only surface through the awkward global search or
a raw `/app/<doctype>` URL unless someone deliberately wires them in.

This app has one workspace: **[`Paymob Integration`](../paymob_integration/paymob_integration/workspace/paymob_integration/paymob_integration.json)**.
It is the front door to everything this app builds, and it is the canonical reference this
rule is checked against — if a link, shortcut, or card described below doesn't match what is
actually in that file, the file is wrong and gets fixed in the same change.

## What must be wired in

Any of the following, once it ships in a slice, is added to the `Paymob Integration` workspace
in the **same change** that adds it — not a follow-up:

| Entity | Goes in as |
|---|---|
| A standalone DocType (not a child table) | A `Link` under the relevant Card Break, and a `Shortcut` if it's something a user opens often (e.g. Settings, a log/list they triage) |
| A Report (Query/Script Report) | A `Link` with `is_query_report: 1` under the relevant Card Break |
| A Page | A `Link` of type `Page`, or a `Shortcut` if it's a primary entry point |
| A Dashboard Chart / Number Card | Added to the workspace `charts` / `number_cards` arrays and referenced in `content` |

**Child tables are exempt** — `Paymob Credential Set` and `Paymob Integration ID` have no list
view of their own and are reached through their parent, so they do not get a workspace entry.

## How to wire it in

1. Add or edit the doctype/report/page as normal.
2. Open the `Paymob Integration` workspace in the Desk (`/app/paymob-integration`) and add the
   Link/Shortcut/Card there — Frappe's workspace editor writes the JSON for you.
3. Export it back to the file so the change is reviewable as a diff, same as any other
   fixture:
   ```bash
   bench --site <site> export-fixtures
   ```
   or edit `paymob_integration/paymob_integration/workspace/paymob_integration/paymob_integration.json`
   directly for small additions (one more `Link` object and, if relevant, one more `Shortcut`
   object and `content` block).
4. Commit the updated workspace JSON alongside the entity it now exposes.

## Definition of Done

- [ ] The new DocType/Report/Page has a `Link` entry in the workspace JSON, under an
      appropriate Card Break (create a new Card Break section if none fits).
- [ ] If it's something a user needs to reach directly and often, it also has a `Shortcut`
      entry.
- [ ] The `content` field's block list includes the new header/shortcut/card ids where
      applicable — an entry that exists in `links`/`shortcuts` but not in `content` is not
      visible in the sidebar.
- [ ] Child tables are **not** added (see exemption above) — don't pad the workspace with
      entries that have nowhere to link to.
- [ ] The workspace JSON is committed in the same change as the entity, per [`slices.md`](slices.md).

## What this rule is NOT

- Not a requirement to design dashboards, number cards, or charts speculatively — add those
  only when a slice actually produces the data behind them.
- Not a second workspace. One app, one workspace (`Paymob Integration`) — do not create a
  personal or module-specific workspace instead of extending the shared one.
- Not a substitute for [`documentation.md`](documentation.md) — a workspace entry makes a
  feature *reachable*; it does not document what the feature *does*.
