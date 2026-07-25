# Rule: Slices

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (blocking at review)

## Why this rule exists

Other rules in this folder say "a slice is not done until…". This file says what a slice is.

The unit matters because of how this app is built: a human directs an AI, then reviews what it
produced. A change that is too big cannot be reviewed properly — the reviewer skims, and
skimming is how a payment defect reaches production. A change that is too small produces docs
and tests for something that does nothing on its own.

## What a slice is

**A slice is one vertical piece of working behaviour, small enough to review carefully in one
sitting.**

Vertical means it goes through every layer it needs — schema, server code, permissions, docs,
tests, translations — rather than being one layer of many features.

Good slices:

- "Create a Paymob intention from a Payment Request and store the returned identifiers."
- "Verify an incoming webhook signature and reject anything that fails."
- "Post a Payment Entry from a verified successful callback, once."

Not slices:

- "Build the webhook handler." Too big — verification, deduplication, amount checking, and
  posting are four separate review problems.
- "Add the settings DocType fields." Not vertical — nothing works at the end of it.

## The requirement

A slice is **done** only when all of these ship in the same change:

| Part | Meaning |
|---|---|
| Code | The behaviour works end to end |
| Schema | DocType JSON committed; any data change has a patch |
| Permissions | Who may trigger it is decided and enforced |
| Tests | Per [`testing.md`](testing.md) |
| Docs | Per [`documentation.md`](documentation.md) — states, decisions, fields, endpoints |
| Translations | Per [`translation.md`](translation.md) |
| Money rules | Per [`payments.md`](payments.md) if it touches money |

Partial slices are not merged. If a slice grows while being built, it is split — not finished
in a hurry.

## Definition of Done

- [ ] The slice does something observable on its own.
- [ ] Every part in the table above shipped in the same change.
- [ ] The change is small enough that the reviewer read every line, not skimmed it.
- [ ] Nothing was left as "to be added in the next slice" without an entry recording it.

## What this rule is NOT

- Not a story-point or estimation system. There is no size in hours here, only "reviewable in
  one sitting".
- Not a ban on refactoring commits or docs-only commits. Those are not slices and do not need
  the full checklist.
