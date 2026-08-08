# Rule: Commit Messages

**Status:** Active · **Since:** 2026-07-26 · **Enforcement:** Convention (blocking at review)

## Why this rule exists

Consistent commit messages make history searchable and let reviewers understand the purpose of a
change without reading its diff.

## The requirement

Every commit uses Conventional Commits:

```
<type>: <concise imperative summary>
```

Use the type that best describes the change: `feat`, `fix`, `docs`, `test`, or `chore`.
Use an optional scope only when it adds useful context, for example `fix(webhook): reject invalid
signatures`. Mark a breaking change with `!` and explain its migration impact in the commit body.

Run `pre-commit run --all-files` before every commit and before every push. CI runs the identical
command in "Run repository checks" — `ruff-format` and other hooks fail the build if they'd modify
a file, so a hook that silently reformats locally must be re-run and its output re-staged before
committing, not left for CI to catch.

## Definition of Done

- [ ] The subject follows `<type>: <summary>`.
- [ ] The type accurately describes the change.
- [ ] The summary is concise and describes the change in the imperative mood.
- [ ] Breaking changes are marked with `!` and explain their migration impact in the body.
- [ ] `pre-commit run --all-files` was run and passed (no files modified) before committing/pushing.

## What this rule is NOT

- Not a requirement for a particular commit tool, branch name, or release automation.
- Not a substitute for a clear pull request description or review.
