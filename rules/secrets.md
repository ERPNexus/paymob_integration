# Rule: Secrets

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention + `pre-commit` (secret scan)

## Why this rule exists

This app holds four credentials that move money or prove identity: the **secret key**, the
**API key**, the **HMAC secret**, and the **public key**. Three of the four are server-only.

A leaked secret key lets someone refund money on the merchant's account. A leaked
HMAC secret lets someone forge a callback and mark unpaid orders as paid — which defeats the
single most important check in [`payments.md`](payments.md).

Secrets leak in boring ways: a debug print, an error page, a test fixture, a screenshot in a
pull request.

## The requirement

### Where secrets live

- Stored on the Settings DocType using the **Password** fieldtype, read with `get_password()`.
  Never a Data field.
- Site-level values may live in `site_config.json`. Never in `hooks.py`, never in a constant,
  never in a default value.
- Test fixtures use obviously fake values (`sk_test_FAKE_...`). Never a real credential, even
  a test-mode one.

### Where secrets must never appear

- Git — including deleted lines, because git history keeps them.
- Logs, at any level, including exception messages and tracebacks.
- API responses, error pages, and anything rendered to a browser.
- Pull request descriptions, screenshots, and issue comments.

### Handling

- The public key is the only credential that may reach the browser.
- Never log a full webhook payload. Log the fields you need, per [`logging.md`](logging.md).
- If a secret is exposed, rotate it in the Paymob dashboard first, then clean it up. Rotation
  comes before cleanup, always.

## Definition of Done

- [ ] New credentials use the Password fieldtype and `get_password()`.
- [ ] No secret value appears in the diff, in tests, or in fixtures.
- [ ] No new code path logs or returns a credential.
- [ ] `pre-commit run --all-files` passes, including the secret scan.

## What this rule is NOT

- Not a key management system. Rotation is manual, done in the Paymob dashboard.
- Not a rule about customer data — what may be stored about a payer is in
  [`stored-payment-data.md`](stored-payment-data.md).
