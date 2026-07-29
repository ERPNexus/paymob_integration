# DESIGN.md — Paymob Integration visual system

> Read this before touching any UI (Desk form scripts, workspace, print/email
> templates, future portal pages). It's the source of truth so different
> sessions don't invent different colors. Generated via `frappe-impeccable
> document`, kept factual — update it the same slice you add real styling.

## App identity

- Frappe v16 app, Desk-only today. No portal pages, no web theme.
- Customizes: the Desk "Apps" launcher tile, one workspace
  (`Paymob Integration`), and the `Payment Request` form (custom buttons via
  `public/js/payment_request.js`).
- No `app_include_css` / `app_include_js` registered yet in `hooks.py` — there
  is currently **zero custom CSS** in this app. Frappe's default Desk theme
  applies everywhere.

## Brand palette

Only one brand color exists so far, taken from the shipped logo
(`public/images/paymob-logo.svg`, class `.a{fill:#0180fd;}`):

| Token | Value | Role |
|---|---|---|
| `--paymob-primary` | `#0180fd` | Paymob brand blue — the only color pulled from brand assets. Use for anything that should read as "Paymob", e.g. a future checkout-status badge or the "Pay with Paymob" button if it's ever restyled off the default Frappe button. |

Everything else — buttons, indicators, form styling — stays **unstyled
Frappe default** (`--primary`, `--red-500`, `--green-500`, etc. from Frappe's
own theme). Do not introduce a second accent color without updating this
table first.

## Override strategy (for when CSS is eventually added)

None registered yet. When a Desk CSS file is added:

1. Create `public/css/paymob_integration.css`, register it via
   `app_include_css` in `hooks.py`.
2. Override Frappe CSS variables with `html:root, :root:root { ... }`
   (specificity 0,2,0 beats Frappe's own `:root` 0,1,0 — no `!important`).
3. Never touch `.standard-actions`, sidebar, form tabs, or login selectors
   directly — style in place, don't hide/move functional Desk DOM (see
   `frappe-impeccable` reference `references/frappe-selectors.md`).

## Surfaces styled

None yet — all default Frappe Desk chrome. The only visual additions are:

- Desk launcher tile logo: `/assets/paymob_integration/images/paymob-mark.svg`
  — a compact square "P" mark (referenced in `hooks.py`
  `add_to_apps_screen`), distinct from the full wordmark used elsewhere.
- Two custom buttons on `Payment Request`: "Pay with Paymob", "Paymob
  Attempts" — plain `frm.add_custom_button`, default Frappe button styling.

## Typography

Frappe default (Inter/system stack). No overrides, no web fonts loaded.

## Email system

**Audience / task / success state:** payers need an unambiguous payment or refund update; accounts
staff need enough context to review an operational event. A successful email makes the state clear
at a glance and gives one relevant next action when action is needed.

All eight payment emails use `paymob_integration.email.render`: ERPNext's native Payment Request
message plus the seven editable Paymob Notification records. It deliberately stays inside
Frappe's native email shell and uses no remote images or web fonts.

| Element | Rule |
|---|---|
| Layout | 600px maximum-width presentation table, fluid at narrow widths, with inline styles only. |
| Brand | `#0180fd` header and plain-text Payment Request Company name; branding remains usable when images are blocked. Paymob is named only where operationally relevant. |
| Card | White detail surface on `#f3f6f9`; 32px inner spacing, 16px body text, and one optional blue CTA. |
| Status | Success `#166534` / `#dcfce7`; action required `#b91c1c` / `#fee2e2`; expiry `#92400e` / `#fef3c7`; info `#075985` / `#e0f2fe`; neutral `#374151` / `#f3f4f6`. Color reinforces an explicit status label; it is never the only signal. |
| RTL | Every content cell uses Frappe's `is_rtl()` Jinja helper to set `dir` plus matching `align`; no `left`/`right` CSS is hardcoded. |

The renderer accepts only app-controlled Jinja fragments. Continue to escape document values by
default; never mark email content or webhook data `safe`.

## Motion

None. No transitions/animations added by this app.

## RTL / i18n

All Arabic strings live in `paymob_integration/translations/ar.csv` (per
`rules/translation.md`). No RTL-specific CSS exists because no CSS exists —
if/when a CSS file is added, it must be checked in both LTR and RTL (Frappe
flips `html[dir=rtl]` automatically; don't hardcode `left`/`right` — use
logical properties or mirror explicitly).

## Key files

- `paymob_integration/hooks.py` — where `app_include_css`, `doctype_js`,
  `add_to_apps_screen` are registered.
- `paymob_integration/public/js/payment_request.js` — the only Desk JS.
- `paymob_integration/public/images/paymob-logo.svg` — brand asset, source of
  `--paymob-primary`.
- `paymob_integration/paymob_integration/workspace/paymob_integration/` —
  workspace layout (icons, cards, shortcuts) — no custom colors, uses
  Frappe's built-in workspace icon set.

## Gotchas

- Don't add a CSS file "just because" — this app has stayed intentionally
  unstyled. Add one only when a real screen (e.g. the future customer result
  page in `plans/03-result-page.md`) needs it, and update this file in the
  same change.
- If a portal/result page is built later (Phase 03), it's a **web page**, not
  Desk — it gets its own `web_include_css`/theme entry, and needs its own
  "Surfaces styled" section here since Desk overrides don't reach it.
- Email clients strip style blocks and may block images. Keep this email system table-based,
  inline-styled, image-independent, and preview it in an inbox before shipping.
