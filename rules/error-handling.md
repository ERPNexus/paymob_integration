# Rule: Error Handling

**Status:** Active · **Since:** 2026-07-25 · **Enforcement:** Convention (blocking at review)

## Why this rule exists

In a payment integration, an error that is swallowed is money that disappears. A `except:
pass` around a Payment Entry creation means the customer paid, the code moved on, and nobody
will ever know — there is no error, no log, and no failed state to retry.

The opposite mistake is just as bad: showing the customer a Python traceback tells an attacker
your file paths, your library versions, and sometimes your data.

## The requirement

### Never swallow

- No bare `except:` and no `except Exception: pass`.
- Every `except` block does at least one of: log a named error, re-raise, or set an explicit
  state that a human or the poller will act on.
- Catching an exception to hide it from the user is only acceptable if the error was recorded
  somewhere a human will actually look.

### Catch narrowly

- Catch the specific exception you can handle. A network timeout and a validation failure are
  different problems and must not share a handler.
- Never wrap a whole function body in one `try`. Wrap the call that can fail.

### Errors do not change payment state

Repeated from [`payments.md`](payments.md) because it is the rule most often broken inside an
`except` block: a failure to *reach* Paymob tells you nothing about the money. It never marks a
payment failed, expired, or paid.

### What the user sees

- User-facing messages are translatable (`_()`), short, and say what to do next.
- They never contain a traceback, a file path, a SQL statement, a credential, or a raw Paymob
  response.
- The detail goes to the log, keyed by the Payment Request name, so support can find it.

### Webhook responses

- A verification failure returns an error status and nothing else — no explanation of *why* it
  failed, because that helps an attacker.
- A message that is authentic but already processed returns HTTP 200, so Paymob stops retrying.
- An internal failure while processing an authentic message returns a non-2xx status, so
  Paymob retries.

## Definition of Done

- [ ] No bare `except` and no silently swallowed exception in the change.
- [ ] Every caught exception is logged with the payment reference or re-raised.
- [ ] No gateway or network error changes payment state.
- [ ] User-facing messages are translatable and leak nothing internal.
- [ ] Webhook status codes follow the three cases above.

## What this rule is NOT

- Not a requirement to catch everything. An unexpected exception reaching Frappe's error log is
  better than a wrong `except` that hides it.
- Not about log format — that is [`logging.md`](logging.md).
