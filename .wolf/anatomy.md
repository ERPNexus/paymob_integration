# anatomy.md

> Auto-maintained by OpenWolf. Last scanned: 2026-07-26T06:11:01.566Z
> Files: 99 tracked | Anatomy hits: 0 | Misses: 0

## ./

- `.editorconfig` — Editor configuration (~109 tok)
- `.eslintrc` (~671 tok)
- `.gitignore` — Git ignore rules (~343 tok)
- `.pre-commit-config.yaml` (~538 tok)
- `AGENTS.md` — Repository Guidelines (~927 tok)
- `CLAUDE.md` — OpenWolf (~1914 tok)
- `license.txt` (~268 tok)
- `pyproject.toml` — Python project configuration (~565 tok)
- `README.md` — Project documentation (~171 tok)

## .agents/skills/teach/

- `GLOSSARY-FORMAT.md` — GLOSSARY.md Format (~531 tok)
- `LEARNING-RECORD-FORMAT.md` — Learning Record Format (~690 tok)
- `MISSION-FORMAT.md` — MISSION.md Format (~386 tok)
- `RESOURCES-FORMAT.md` — RESOURCES.md Format (~481 tok)
- `SKILL.md` — Teaching Workspace (~2375 tok)

## .agents/skills/teach/agents/

- `openai.yaml` (~40 tok)

## .claude/

- `settings.json` (~441 tok)

## .claude/rules/

- `openwolf.md` (~313 tok)

## .frappe-visual-review/2026-07-26T05-19-47/

- `report.json` (~670 tok)

## .frappe-visual-review/2026-07-26T05-45-03/

- `report.json` (~1264 tok)

## .frappe-visual-review/2026-07-26T05-47-41/

- `report.json` (~722 tok)

## .ruff_cache/

- `.gitignore` — Git ignore rules (~10 tok)
- `CACHEDIR.TAG` (~12 tok)

## .ruff_cache/0.14.10/

- `10976157832668008079` (~152 tok)
- `8546099780309061464` (~152 tok)

## docs/

- `architecture.md` — Architecture — How a Paymob ↔ ERPNext Payment Actually Flows (~2416 tok)
- `glossary.md` — Glossary — Paymob & Payment-Integration Terms (~5010 tok)
- `must_have_features.md` — Must-Have Features — Non-Negotiables for the Paymob ↔ ERPNext Integration (~2228 tok)
- `README.md` — Project documentation (~383 tok)
- `references.md` — References (~1487 tok)

## docs/developer-guide/

- `README.md` — Project documentation (~191 tok)

## docs/reference/

- `decisions.md` — Decisions (ADRs) (~1054 tok)
- `endpoints.md` — Endpoints, Settings & Errors (~882 tok)
- `fields.md` — Fields (~2081 tok)
- `README.md` — Project documentation (~381 tok)
- `states.md` — States & Transitions (~763 tok)

## docs/user-guide/

- `README.md` — Project documentation (~1601 tok)

## learning/paymob-integration/

- `learning_checklist.md` — Learning Checklist — Explain These Unprompted Before Writing the Code (~1807 tok)
- `learning_progress.md` — Learning Progress — Paymob ↔ ERPNext Integration (~1563 tok)
- `plan.md` — Paymob Integration Learning Plan (~744 tok)
- `resources.md` — Learning Resources (~331 tok)
- `session-log.md` — Session Log (~8673 tok)

## paymob_integration/

- `__init__.py` (~7 tok)
- `hooks.py` — Declares views (~1935 tok)
- `modules.txt` (~5 tok)
- `patches.txt` (~73 tok)

## paymob_integration/config/

- `__init__.py` (~0 tok)

## paymob_integration/patches/

- `__init__.py` (~0 tok)

## paymob_integration/paymob/

- `__init__.py` (~0 tok)
- `auth.py` — API key to Bearer auth token, used by Transaction Inquiry. (~212 tok)
- `client.py` — The only module that talks to the network. Every Paymob call goes through request(). (~438 tok)
- `settings.py` — Read Paymob Settings. No other module opens that doctype directly. (~300 tok)

## paymob_integration/paymob_integration/

- `__init__.py` (~0 tok)
- `.frappe` (~0 tok)

## paymob_integration/paymob_integration/doctype/

- `__init__.py` (~0 tok)

## paymob_integration/paymob_integration/doctype/paymob_credential_set/

- `__init__.py` (~0 tok)
- `paymob_credential_set.json` (~562 tok)
- `paymob_credential_set.py` — For license information, please see license.txt (~62 tok)

## paymob_integration/paymob_integration/doctype/paymob_integration_id/

- `__init__.py` (~0 tok)
- `paymob_integration_id.json` (~422 tok)
- `paymob_integration_id.py` — For license information, please see license.txt (~62 tok)

## paymob_integration/paymob_integration/doctype/paymob_settings/

- `__init__.py` (~0 tok)
- `paymob_settings.js` — For license information, please see license.txt (~250 tok)
- `paymob_settings.json` (~485 tok)
- `paymob_settings.py` — For license information, please see license.txt (~228 tok)

## paymob_integration/paymob_integration/workspace/paymob_integration/

- `paymob_integration.json` (~445 tok)

## paymob_integration/public/

- `.gitkeep` (~0 tok)

## paymob_integration/templates/

- `__init__.py` (~0 tok)

## paymob_integration/templates/pages/

- `__init__.py` (~0 tok)

## paymob_integration/translations/

- `ar.csv` (~313 tok)

## plans/

- `01-settings-and-credentials.md` — Phase 01 — Settings & Credentials Implementation Plan (~8010 tok)
- `02-create-intention-and-checkout.md` — Phase 02 — Intention & Checkout URL Implementation Plan (~7652 tok)
- `03-result-page.md` — Phase 03 — Customer Result Page (outline) (~449 tok)
- `04-webhook-hmac-verification.md` — Phase 04 — Webhook & HMAC Verification (outline) (~407 tok)
- `05-transaction-record-and-dedup.md` — Phase 05 — Transaction Record & Dedup (outline) (~443 tok)
- `06-state-machine-and-audit.md` — Phase 06 — State Machine & Audit Trail (outline) (~419 tok)
- `07-amount-verification.md` — Phase 07 — Amount Verification (outline) (~303 tok)
- `08-ledger-write-path.md` — Phase 08 — The Single Ledger Write Path (outline) (~402 tok)
- `09-duplicate-payment-guard.md` — Phase 09 — Duplicate Payment Guard (outline) (~276 tok)
- `10-reconciliation-poller.md` — Phase 10 — Reconciliation & Expiry (outline) (~414 tok)
- `11-refund-and-void.md` — Phase 11 — Refund & Void (outline) (~442 tok)
- `12-pre-go-live-verification.md` — Phase 12 — Pre-Go-Live Verification (outline) (~426 tok)
- `README.md` — Project documentation (~2946 tok)

## rules/

- `audit-trail.md` — Rule: Audit Trail (~630 tok)
- `commits.md` — Rule: Commit Messages (~336 tok)
- `configuration.md` — Rule: Configuration (~626 tok)
- `currency.md` — Rule: Currency (~503 tok)
- `documentation.md` — Rule: Documentation Discipline (~877 tok)
- `error-handling.md` — Rule: Error Handling (~675 tok)
- `frappe-discipline.md` — Rule: Frappe Discipline (~727 tok)
- `implementation-gate.md` — Implementation Gate — must-not-get-wrong list (~1432 tok)
- `logging.md` — Rule: Logging (~676 tok)
- `payments.md` — Rule: Money Safety (~1390 tok)
- `README.md` — Project documentation (~866 tok)
- `secrets.md` — Rule: Secrets (~552 tok)
- `slices.md` — Rule: Slices (~672 tok)
- `stored-payment-data.md` — Rule: Stored Payment Data (~598 tok)
- `testing.md` — Rule: Testing (~796 tok)
- `translation.md` — Rule: Translation (~801 tok)
- `workspace.md` — Rule: Workspace Visibility (~960 tok)
