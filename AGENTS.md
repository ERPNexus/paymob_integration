# Repository Guidelines

## Claude-Managed Repository

This repository is managed with Claude. Codex and all other coding agents must read and follow `CLAUDE.md`, `.claude/`, and the user's Claude configuration before making changes, and should work with the same conventions and behavior as Claude. When instructions conflict, follow the instruction with the highest system-defined precedence.

## Repository Rules (read before writing code)

Deep, repo-specific commitments live in [`rules/`](rules/), not in this file. Read
[`rules/README.md`](rules/README.md) first, and [`rules/payments.md`](rules/payments.md) before
touching any code path that moves money. Each rule ends with a Definition of Done checklist —
those checklists are the review gate. Where this file and a rule appear to overlap, the rule is
the detailed and authoritative version.

## Project Structure & Module Organization

This repository is a Frappe app named `paymob_integration` for ERPNext/Bench. Core app metadata and hooks live in `paymob_integration/hooks.py`, with module declarations in `paymob_integration/modules.txt` and migration entries in `paymob_integration/patches.txt`. Place Python package code under `paymob_integration/`, Frappe module code under `paymob_integration/paymob_integration/`, static assets under `paymob_integration/public/`, website templates under `paymob_integration/templates/`, and route pages under `paymob_integration/www/`. Project notes and design references are in `docs/`.

## Build, Test, and Development Commands

Run commands from the Bench root unless noted.

- `bench get-app <repo-url> --branch version-16`: install this app into a Bench.
- `bench --site <site-name> install-app paymob_integration`: install the app on a site.
- `cd apps/paymob_integration && pre-commit install`: enable local formatting and lint checks.
- `cd apps/paymob_integration && pre-commit run --all-files`: run Ruff, Prettier, ESLint, and repository checks.
- `bench --site <site-name> migrate`: apply DocType and patch changes after schema edits.
- `bench --site <site-name> run-tests --app paymob_integration`: run app tests when tests are added.

## Coding Style & Naming Conventions

Use tabs for Python, JavaScript, Vue, CSS, SCSS, and HTML, matching `.editorconfig` and Ruff formatting. JSON DocType files use one-space indentation and no final newline. Python targets 3.14, uses double quotes, and follows Ruff rules in `pyproject.toml` with import sorting enabled. Keep Frappe hooks explicit in `hooks.py`; name modules, DocTypes, and files after the business concept they implement.

## Testing Guidelines

No test suite is present yet. Add Python tests close to the feature, using Frappe conventions such as `test_*.py`, then run `bench --site <site-name> run-tests --app paymob_integration`. For payment flows, cover successful callbacks, failed callbacks, duplicate webhook delivery, signature validation, and permission boundaries. Prefer deterministic fixtures over live Paymob calls.

## Commit & Pull Request Guidelines

Git history currently uses Conventional Commits, for example `feat: Initialize App`. Continue with concise prefixes such as `feat:`, `fix:`, `docs:`, `test:`, and `chore:`. Pull requests should include a short problem statement, implementation summary, test evidence, migration notes if any, linked issues, and screenshots for Desk or website UI changes.

## Security & Configuration Tips

Do not commit Paymob API keys, HMAC secrets, site configs, logs, caches, or Bench runtime state. Store credentials in site configuration or secure Frappe settings. Validate all webhook input, avoid logging sensitive payload fields, and keep callback endpoints permission-aware.
