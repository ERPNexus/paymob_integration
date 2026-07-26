# Repository Rules

Conventions this repository commits to. Each rule states *why* it exists, *what* it requires,
and *how* it is enforced. Rules are followed by both human contributors and AI agents building
in this repo.

**Read [`payments.md`](payments.md) first.** This app moves money; that rule is the one that
blocks a merge.

## The rules

### Money

| Rule | Purpose | Enforcement |
|---|---|---|
| [payments.md](payments.md) | The 18 requirements for any code path that touches money | Convention (blocking at review) |
| [currency.md](currency.md) | An amount is never compared or stored without its currency | Convention (Definition of Done) |
| [audit-trail.md](audit-trail.md) | Money-affecting events leave a durable, immutable record | Convention (blocking at review) |
| [stored-payment-data.md](stored-payment-data.md) | Card data never enters this app — the PCI boundary | Convention (blocking at review) |

### Building

| Rule | Purpose | Enforcement |
|---|---|---|
| [slices.md](slices.md) | What a unit of work is, and when it is done | Convention (blocking at review) |
| [testing.md](testing.md) | The payment scenarios every money path must prove | Convention (blocking at review) |
| [documentation.md](documentation.md) | Every slice ships with docs; published docs 100% cover the app | Convention (Definition of Done) |
| [translation.md](translation.md) | Every user-facing string is translatable; Arabic lives in `ar.csv` | Convention (Definition of Done) |
| [workspace.md](workspace.md) | Every new DocType, report, or page is reachable from the `Paymob Integration` workspace | Convention (Definition of Done) |

### Craft

| Rule | Purpose | Enforcement |
|---|---|---|
| [frappe-discipline.md](frappe-discipline.md) | Use the Frappe APIs that keep validation, not the ones that skip it | Convention (blocking at review) |
| [error-handling.md](error-handling.md) | No swallowed errors; failures never change payment state | Convention (blocking at review) |
| [logging.md](logging.md) | Every payment stage is traceable by Payment Request name | Convention (Definition of Done) |
| [configuration.md](configuration.md) | Nothing configurable is hardcoded; one Settings DocType | Convention (Definition of Done) |
| [secrets.md](secrets.md) | Credentials never reach git, logs, or the browser | Convention + `pre-commit` |
| [commits.md](commits.md) | Commit history uses a consistent Conventional Commits format | Convention (blocking at review) |

### The gate

[implementation-gate.md](implementation-gate.md) is not a fifteenth rule — it is the review
checklist the rules above were distilled from. It keeps the attack or failure behind each
requirement, and it is what a finished slice is walked against, item by item.

## How these are used

1. **When planning a slice** — the rules are the constraints the plan is written against.
2. **When directing an AI to build it** — the relevant rules go into the instructions.
3. **When reviewing what came back** — the Definition of Done checklists are the review, item
   by item. A slice that fails one is not merged.

## Adding a rule

Keep each rule in its own file, with: **Status / Since / Enforcement** header, a "Why" section,
the concrete requirement, a **Definition of Done** checklist, and an explicit "What this is
NOT" to bound scope. Prefer convention (discipline at review) over automation until a gap
actually recurs.

Rules describe commitments. Study notes and teaching material belong in the gitignored
`learning/`; published product documentation belongs in [`../docs/`](../docs/).
