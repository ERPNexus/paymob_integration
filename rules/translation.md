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
| Canonical external technical term | "Public Key", "HMAC Secret", "Integration ID" | **Arabic + exact English name** — it must match the vendor's dashboard and documentation |

Arabic column names break queries, API calls, reports, and every line of Python that touches
the field. Code stays English. Only what the user reads is translated.

Use clear, concise Modern Standard Arabic. Do not use dialect, literal English syntax, or an
isolated dictionary meaning that obscures the user-visible purpose. Read the field description or
call site before translating an ambiguous term. For example, merchant-facing `Intention` copy
describes the payment session or link that starts checkout, not the literal Arabic word for
"intention."

When a label is the exact name of a Paymob credential, API field, protocol term, or dashboard
value, translate it and retain the exact English name in parentheses, such as `المفتاح السري
(Secret Key)`. This lets a merchant understand the label and match it to Paymob's dashboard.

## Approved payment glossary

| English | Arabic |
|---|---|
| Attempt | محاولة دفع |
| Checkout | صفحة الدفع |
| Pending | قيد الانتظار |
| Reconciliation | المطابقة الآلية |
| Refund | استرداد |
| Void | إلغاء |
| Reversal | عكس عملية الدفع |
| Audit Entry | سجل تدقيق |
| Credentials | بيانات الاعتماد |
| Smallest currency unit | أصغر وحدة نقدية |

## The requirement

- Python: wrap user-facing text in `_()` — `frappe._` — including `frappe.throw` and
  `frappe.msgprint` messages.
- JavaScript and client scripts: wrap in `__()`.
- Jinja templates: use `{{ _("...") }}`.
- Never build a sentence by joining translated pieces. Translate the whole sentence and pass
  values as parameters, because word order differs in Arabic.
- All runtime Arabic text lives in `paymob_integration/translations/ar.csv`; the approved glossary
  in this rule is documentation, not an application translation source.
- Select options are translated for display; the value stored in the database stays English so
  code and reports keep working.
- Quote all three CSV fields: `"source","translation","context"`. Preserve the exact source text,
  require unique source/context pairs, and keep every `{0}`, `{1}`, etc. placeholder identical on
  both sides.

## Definition of Done

- [ ] Every new user-facing string is wrapped in `_()` / `__()` / `{{ _() }}`.
- [ ] No sentence is assembled from concatenated translated fragments.
- [ ] New strings have Arabic entries in `translations/ar.csv`.
- [ ] No runtime Arabic text appears outside `ar.csv` (the glossary above is documentation only).
- [ ] No fieldname, DocType name, or stored value was translated.
- [ ] Canonical Paymob dashboard, API, and protocol terms retain their English spelling.
- [ ] Every CSV row has three quoted fields, an exact source key, a unique source/context pair, and
  matching placeholders.
- [ ] Each Arabic translation makes sense without consulting its English source.

## What this rule is NOT

- Not a requirement to translate developer-facing text: log lines, exception text meant for
  `error_log`, and code comments stay English.
- Not a right-to-left layout rule. If a customer-facing page is added later, RTL layout is a
  separate piece of work and gets its own decision entry in `docs/reference/decisions.md`.
