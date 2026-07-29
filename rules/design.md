# Rule: Design System Discipline

**Status:** Active · **Since:** 2026-07-29 · **Enforcement:** Convention (blocking at review)

## Why this rule exists

Visible product surfaces become inconsistent when each slice invents its own visual choices.
[`DESIGN.md`](../DESIGN.md) is the app's source of truth for the small set of choices that should
remain consistent across Desk, web, print formats, and email.

## The requirement

Before styling a Desk form, web page, print format, or email, identify its audience, task, and
success state. Reuse documented Frappe patterns and `DESIGN.md` tokens before introducing a new
visual choice.

When a slice adds a color, type scale, spacing rule, component pattern, asset, or motion, update
`DESIGN.md` in that same slice. Every visible surface uses accessible contrast, meaningful status
semantics, responsive layout, and RTL-safe logical alignment; interactive Desk and web controls
also remain keyboard-safe.

Validate the finished presentation with screenshots for Desk/web, rendered previews for print
formats, and inbox previews for email.

Customer-facing payment email branding comes from the linked Payment Request's Company. Paymob may
be named only where it helps explain an operational payment action; the configured site Email Account
supplies the delivery identity.

## Definition of Done

- [ ] Audience, task, and success state are clear from the surface and its copy.
- [ ] Existing Frappe patterns and `DESIGN.md` tokens were reused where they apply.
- [ ] `DESIGN.md` changed with any new visual token, component, asset, type, spacing, or motion.
- [ ] Contrast and status meaning are accessible; layout is responsive and RTL-safe.
- [ ] Desk/web interaction is keyboard-safe where applicable.
- [ ] The relevant screenshot, rendered preview, or inbox preview was reviewed.

## What this rule is NOT

- Not permission for a speculative redesign, a new UI framework, or global cosmetic CSS without a
  real surface that needs it.
- Not a substitute for Frappe's native controls or accessibility behaviour.
