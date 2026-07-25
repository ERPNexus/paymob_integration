# Reference Registries

The **source of truth** for how the app behaves. Four registries, each an append-and-maintain
list of entries. Governed by [`../../rules/documentation.md`](../../rules/documentation.md).

| Registry | Covers |
|---|---|
| [states.md](states.md) | Payment/record lifecycle states and review flags |
| [fields.md](fields.md) | DocType fields that carry meaning |
| [decisions.md](decisions.md) | ADRs — the *why* behind non-obvious choices |
| [endpoints.md](endpoints.md) | Endpoints, settings, and named error paths |

## The entry format: one entry, two lenses

Every entry has both views. If you can't write the Functional line, the feature isn't clear
enough to ship; if you can't write the Technical block, it isn't built correctly yet.

```markdown
### <Name of the thing>

**Functional:** One or two plain-language sentences — what the user or business sees, why it matters.

**Technical:**
- <the exact trigger / rule / source of truth>
- <code touchpoint, constraint, or transition>
- <edge cases or "do NOT" rules>
```

## Rules for good entries

- **Functional first, always fillable.** Written for someone who does not read the code.
- **Technical is exact.** Name the actual field, endpoint, status, or transition — not "somewhere in the code."
- **One source of truth.** Do not restate an entry in a guide; link to it.
- **Record the "do NOT" rules.** The dangerous, non-obvious constraints (e.g. "never write the
  ledger from the browser callback") are the highest-value lines here.
