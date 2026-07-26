# OpenWolf

@.wolf/OPENWOLF.md

This project uses OpenWolf for context management. Read and follow .wolf/OPENWOLF.md every session. Check .wolf/cerebrum.md before generating code. Check .wolf/anatomy.md before reading files.


# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository currently is

A Frappe app (`paymob_integration`) that integrates Paymob payments with ERPNext. **Almost no
implementation exists yet.** `paymob_integration/hooks.py` is untouched boilerplate — every hook is
commented out. There are no DocTypes, no tests, and no Python modules beyond empty `__init__.py`
files.

What *does* exist is the design layer, and it is the point of this repo:

| Folder | Contains | Audience |
|---|---|---|
| `rules/` | 14 repo commitments, each ending in a Definition of Done checklist | contributors + AI agents |
| `plans/` | 12 numbered build phases, in payment-lifecycle order | whoever builds the next slice |
| `docs/` | published product documentation (ships with the app) | merchants, integrating developers |
| `learning/` | the owner's private study notes — gitignored, **not shipped, not a spec** | owner only |

Read `rules/README.md` and `plans/README.md` before writing code. Where this file and a rule
overlap, **the rule is authoritative**. `AGENTS.md` is the same pointer for non-Claude agents; keep
the two in sync rather than duplicating rule content into either.

## Commands

Run from the **bench root** (`/home/frappe/frappe-bench-16`) unless noted.

```bash
bench --site <site> install-app paymob_integration
bench --site <site> migrate                              # after any DocType or patch change
bench --site <site> run-tests --app paymob_integration
bench --site <site> run-tests --module paymob_integration.paymob_integration.doctype.<dt>.test_<dt>
bench --site <site> run-tests --doctype "Paymob Transaction"
bench build --app paymob_integration                     # only if public/ assets are added
```

From `apps/paymob_integration`:

```bash
pre-commit install            # once
pre-commit run --all-files    # ruff, eslint, prettier, pyupgrade — must pass before commit
```

There is no pytest setup. Tests are Frappe `unittest`-style `test_*.py` files living next to the
DocType they cover. `--module` is the way to run one file; there is no single-test-method runner.

## Architecture (what is being built)

The payment lifecycle, and the file layout it implies, is fixed by `plans/README.md`. Six ideas
carry most of the design; each is an ADR in `docs/reference/decisions.md`.

**A `Paymob Payment Attempt` DocType owns lifecycle state — not the Payment Request.** A retry is a
new attempt with a new `special_reference`, and `failed` is terminal *for that attempt only*. Fields
on the Payment Request cannot express "one failed attempt plus one pending attempt".

**There is exactly one function that creates Payment Entries.** Grepping for "who inserts a Payment
Entry" must return one answer, forever. It delegates to ERPNext's own
`PaymentRequest.create_payment_entry`, which builds the allocation and reference rows correctly;
the clearing account is set on the **in-memory** Payment Request before the call and never saved.

**Money is written from verified inbound facts, never from an outbound API response.** A ledger
entry comes from a webhook that passed HMAC-SHA512 verification, or from a Transaction Inquiry
result. The HTTP response to a capture/refund call is not evidence — the request may have succeeded
with the response lost.

**Three independent checks gate every posting:** authenticity (HMAC), success state, and amount +
currency match against a snapshot. All three pass or nothing posts. An amount mismatch on an
authentic message is audited for a human, never auto-posted.

**The webhook endpoint is the only `allow_guest=True` method in the app.** Paymob's servers have no
Frappe session; the HMAC is the authentication, checked before any document load or database read.
Every other money-moving `@frappe.whitelist()` method checks permission on the document first, and
never trusts a browser-supplied amount or reference.

**Duplicates are handled differently in each direction.** Inbound: a unique database constraint on
`event_key = "<transaction_id>:<event_kind>"` — a constraint, not an `if`. Outbound: a server-side
row lock taken *before* the request, because a capture/refund has no ID until the call creates one
and Paymob accepts no idempotency key.

Recovery is a scheduled poller (`plans/10`) that inquires on pending attempts — because Paymob's
webhook retry behaviour is undocumented and is assumed to be zero.

## Constraints that block a merge

The full list is `rules/payments.md` (18 requirements) and the "Global constraints" section of
`plans/README.md`. The ones most easily violated:

- Payment Request status is **derived** from submitted Payment Entries — never `db_set`. `db_set` is
  allowed only on non-money bookkeeping fields such as `last_polled_at`.
- Money is **integer cents**. No float arithmetic, no float equality. Every amount is stored with
  its currency code, and currency is part of the match check. Never default to `"EGP"`.
- `hmac.compare_digest`, never `==`.
- Reads (Transaction Inquiry) may be retried automatically. **Capture, refund and void may never
  be.** Re-running one is a human decision.
- A 401, timeout, or 5xx never changes payment state. Auth-token expiry ≠ intention expiry.
- Credentials use the **Password** fieldtype with `get_password()`, never `Data`. Only the public
  key and the per-session client secret may reach the browser. Never log a credential, card data,
  or a full webhook payload.
- Card PAN/CVV never enter this app — hosted checkout only. Last-4, brand, and Paymob IDs are fine.
- **No test makes a network call**, ever; `requests.request` is patched. Money assertions count
  Payment Entry rows and check allocations — "it did not raise" proves nothing.
- No bare `except`, no `except Exception: pass`. Failures never change payment state.
- Every payment log line carries the **Payment Request name**, via `frappe.logger("paymob")`.

## Conventions

- **Tabs** for Python, JS, CSS, HTML. Double quotes. Ruff, `line-length = 110`, target `py314`.
- **DocType JSON** uses one-space indentation and no final newline — Frappe writes these; commit
  them with the change and do not reformat by hand.
- Every user-facing string is wrapped in `_()` (Python), `__()` (JS), or `{{ _() }}` (Jinja). Never
  build a sentence from concatenated translated fragments. All Arabic lives in
  `paymob_integration/translations/ar.csv` and nowhere else. Fieldnames, DocType names, and stored
  Select values stay English.
- Data changes go through an **idempotent** patch registered in `patches.txt`.
- Commit messages follow [`rules/commits.md`](rules/commits.md).

## Working on a phase

1. Read the whole `plans/NN-*.md` file first. Phases 01 and 02 are written out in full and are the
   worked example of the format; 03–12 are outlines to be expanded immediately before building.
2. Write the test, **run it, and watch it fail** before implementing.
3. Docs are part of the slice, not a follow-up: new states, decisions, fields, endpoints, settings,
   and error paths go into the matching registry under `docs/reference/` in the same change. Each
   registry entry carries both a Functional and a Technical view (`docs/reference/README.md`).
4. Finish by walking the phase's Definition of Done and then
   `rules/implementation-gate.md` against the diff. An unticked box means the phase is split,
   not merged.
