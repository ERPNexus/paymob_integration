# Paymob Integration — Documentation

**Published product documentation** for the `paymob_integration` app. Everything here is meant
to ship with the app so that consumers can understand and use it.

> Personal learning/study notes are **not** here — they live in the gitignored `learning/`.
> The convention that keeps these docs complete is [`../rules/documentation.md`](../rules/documentation.md).

## Layout (by audience)

| Path | Audience | Contents |
|---|---|---|
| [`user-guide/`](user-guide/) | Merchant / end-user | How to configure and operate Paymob payments inside ERPNext |
| [`developer-guide/`](developer-guide/) | Integrator / developer | Install, configure, extend, and integrate the app |
| [`reference/`](reference/) | Both (source of truth) | The four registries: states, fields, decisions, endpoints |

## Existing technical references

- [`architecture.md`](architecture.md) — end-to-end payment data-flow narrative, including failure paths.
- [`glossary.md`](glossary.md) — verified Paymob and ERPNext terminology.
- [`must_have_features.md`](must_have_features.md) — production requirements and scope.
- [`references.md`](references.md) — primary sources with access dates and known unknowns.

## How the reference registries work

Each registry entry is written **once**, with a **Functional** view (plain language) and a
**Technical** view (triggers, rules, code touchpoints) — so the two can never drift apart.
See [`reference/README.md`](reference/README.md) for the entry template and the discipline.
