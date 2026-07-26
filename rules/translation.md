# Rule: Translation

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (Definition of Done)

## Why this rule exists

Paymob's users are Arabic speakers. A merchant must be able to switch the site to Arabic and
see this app — its fields, buttons, messages, and errors — in Arabic, without any code change.

That only works if every readable string passes through Frappe's translation system from the
day it is written. Strings added without `_()` are invisible to the translation file and stay
English forever, and nobody goes back to find them.

## What gets translated, and what must not

| Thing | Example | Translated? |
|---|---|---|
| Fieldname (database column) | `paymob_transaction_id` | **Never** — it is a code identifier |
| DocType name, module name, file name | `Paymob Settings` | **Never** |
| Field label | "Transaction ID" | Yes |
| Button, message, error, notification | "Payment verified" | Yes |
| Select field options | "Pending", "Expired" | Yes — the stored value stays English |
| Print formats, emails, portal pages | receipt template | Yes |
| Canonical external technical term | "Public Key", "HMAC Secret", "Integration ID" | **Keep English** — it must match the vendor's dashboard and documentation |

Arabic column names break queries, API calls, reports, and every line of Python that touches
the field. Code stays English. Only what the user reads is translated.

An English label is also retained when it is the exact name of a Paymob credential, API field,
protocol term, or dashboard value. Translate the surrounding instruction, help text, and error
message, but not the canonical term itself. This lets a merchant match the field to Paymob's
dashboard without guessing whether an Arabic synonym means the same credential.

## The requirement

- Python: wrap user-facing text in `_()` — `frappe._` — including `frappe.throw` and
  `frappe.msgprint` messages.
- JavaScript and client scripts: wrap in `__()`.
- Jinja templates: use `{{ _("...") }}`.
- Never build a sentence by joining translated pieces. Translate the whole sentence and pass
  values as parameters, because word order differs in Arabic.
- All Arabic text lives in `paymob_integration/translations/ar.csv`. It is the only file that
  contains Arabic.
- Select options are translated for display; the value stored in the database stays English so
  code and reports keep working.

## Definition of Done

- [ ] Every new user-facing string is wrapped in `_()` / `__()` / `{{ _() }}`.
- [ ] No sentence is assembled from concatenated translated fragments.
- [ ] New strings have Arabic entries in `translations/ar.csv`.
- [ ] No Arabic text appears anywhere outside `ar.csv`.
- [ ] No fieldname, DocType name, or stored value was translated.
- [ ] Canonical Paymob dashboard, API, and protocol terms retain their English spelling.

## What this rule is NOT

- Not a requirement to translate developer-facing text: log lines, exception text meant for
  `error_log`, and code comments stay English.
- Not a right-to-left layout rule. If a customer-facing page is added later, RTL layout is a
  separate piece of work and gets its own decision entry in `docs/reference/decisions.md`.
