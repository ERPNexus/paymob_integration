# User-Facing Document Reference Links

When a user-facing Python or JavaScript message names a concrete Frappe document, make that
reference clickable whenever the document name is available in the current execution context.

## Python

- Use `frappe.utils.get_link_to_form(doctype, name)` for document references in
  `frappe.throw`, `frappe.msgprint`, warnings, and returned user-facing messages.
- Guard optional references before calling the helper; use a translated generic fallback when no
  document exists. Do not perform unrelated database queries solely to decorate a message.
- Keep generic validation text, counts, and capacity-only notices plain when no concrete record
  is being referenced.

## JavaScript

- Use `frappe.utils.get_form_link(doctype, frm.doc.name)` when the current form provides the
  concrete record. Add links to callbacks only when the response includes actual document names.
- Leave generic counts, status-only notices, and capacity messages unlinked.

## Translations and tests

- Preserve the exact translatable source string and add its Arabic row to
  `cre8tiv_schools/translations/ar.csv` whenever a message’s wording changes.
- Add a focused regression assertion for important validation messages, including every related
  document link expected in the message.
