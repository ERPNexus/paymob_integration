# Rule: Documentation Discipline

**Status:** Active · **Since:** 2026-07-21 · **Enforcement:** Convention (Definition of Done)

## Why this rule exists

This app moves money. When it is published, its documentation must **100% cover how it
works** — a developer must be able to integrate it, a merchant must be able to operate it,
and a reviewer must be able to check any behavior against a written intent. Docs written
"later" are never written. So documentation is part of building a slice, not a follow-up to it.

This rule is **forward-looking**: it does not demand we back-fill everything today. It demands
that from now on, **no slice is "done" until its docs are updated.**

## What must be documented

Four categories. Each lives in a registry under [`../docs/reference/`](../docs/reference/):

| Category | Registry | You must document… |
|---|---|---|
| **States & transitions** | `states.md` | every payment/record state or review flag: meaning, when entered, what exits it, terminal or not |
| **Decisions** | `decisions.md` | the *why* behind any non-obvious choice, ADR-style: context, decision, consequences |
| **Fields** | `fields.md` | every DocType field that carries meaning: what it holds, source of truth, validation, mutability |
| **Endpoints, settings & errors** | `endpoints.md` | callback/API endpoints (auth, side effects), config settings (purpose, default), and named failure paths |

If a change touches user- or developer-facing behavior, the matching guide
(`docs/user-guide/`, `docs/developer-guide/`) is updated too.

## The format: one entry, two lenses

Every registry entry is written **once** with both a functional and a technical view, so they
can never drift out of sync:

- **Functional** — plain language: what the user or the business sees / why it matters.
- **Technical** — the trigger, source of truth, code touchpoints, exact rules.

See [`../docs/reference/README.md`](../docs/reference/README.md) for the entry template.

## Definition of Done (the actual gate)

A slice is **not done** until every box is true:

- [ ] New/changed **states or review flags** are in `states.md`.
- [ ] Any non-obvious **decision** made while building it is an entry in `decisions.md`.
- [ ] New/changed **DocType fields** are in `fields.md`.
- [ ] New/changed **endpoints, settings, or error paths** are in `endpoints.md`.
- [ ] User- or developer-facing behavior changes are reflected in the matching guide.
- [ ] Each entry has **both** a Functional and a Technical view.
- [ ] The app `README.md` is updated if the slice changes installation, setup, or what the app
      does at a high level.

## How this ties into code review (the mission)

The point of colocation is a fast review question you can answer in seconds:

> *"Does the functional meaning of this entry match the technical trigger the generated code
> actually implements?"*

When directing an AI to build a slice, require the doc updates **in the same change** as the
code. Reject a slice whose behavior is not documented, exactly as you would reject one whose
secret key leaks to the browser — undocumented money-movement is a defect.

## What this rule is NOT

- Not a demand to document trivial/private helpers or obvious CRUD.
- Not automated (no pre-commit/CI check) — enforced by discipline at review time. If gaps
  recur despite discipline, revisit and consider adding an automated check then (YAGNI until then).
- Not a place for personal study notes — those live in the gitignored `learning/`.
