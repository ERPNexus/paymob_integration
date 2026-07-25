# Rule: Configuration

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (Definition of Done)

## Why this rule exists

A hardcoded value is a value that cannot be changed without a developer, cannot differ between
test and live, and cannot be found by someone reading the settings page.

In this app the risk is concrete. Paymob has separate regional platforms with different base
URLs, and separate test and live credentials. A base URL written into the code means a merchant
in another country cannot use the app at all, and a mode flag written into the code means
someone will ship test mode to production, or worse, live mode to a test site.

## The requirement

### One place for settings

- All configuration lives on the Paymob Settings DocType, or on the child table of integration
  IDs where the value is per payment method.
- Nothing configurable lives in `hooks.py`, in a module constant, or as a default argument.

### What must be configurable

- The regional base URL.
- Test or live mode, and the credentials belonging to each mode.
- Integration IDs, as a child table: payment method, currency, mode, ID. One field cannot hold
  them, because each ID is a separate contract with its own lifecycle.
- Timeouts and the poller interval.
- Which ERPNext account a payment posts to.

### Mode safety

- Test and live credentials never mix in one request. A live secret key with a test integration
  ID must fail clearly, not silently produce a broken checkout.
- The current mode is visible on the settings page without reading a key.

### Validation at the boundary

- Settings are validated when saved, not when a payment is attempted. A missing HMAC secret is
  found by the merchant on the settings page, not by a customer at checkout.
- A payment attempt with incomplete settings fails with a clear, translatable message.

## Definition of Done

- [ ] No URL, timeout, mode flag, or account name is hardcoded in the change.
- [ ] New settings are on the Settings DocType, with a label, a description, and a default
      where one makes sense.
- [ ] New settings are validated on save.
- [ ] New settings are documented in `docs/reference/endpoints.md` per
      [`documentation.md`](documentation.md).

## What this rule is NOT

- Not a rule about secret storage — that is [`secrets.md`](secrets.md).
- Not a demand to make everything configurable. Values that have exactly one correct answer,
  such as the HMAC field order Paymob defines, stay in the code.
