# Phase 03 — Customer Result Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** The customer's browser lands on `/paymob-result` after checkout and sees a status
message driven by *our own stored* `Paymob Payment Attempt.state` — never by the URL parameters
Paymob puts on the redirect. Phase 02 already sends every customer here
(`paymob_integration/api.py:13,35`); today the route has no handler, so every completed checkout
ends in a 404.

**Architecture:** The redirect's HMAC has no ledger authority (ADR-0001) — it can be replayed —
so it only decides whether the page is *allowed to show* the attempt's real state or must fall
back to the neutral `Pending` one. The page never writes anything: no `db_set`, no `save`, no
state transition. A second module, `paymob/hmac_verify.py`, gets its first real content: the
**response callback** field list and verifier (the **processed callback**'s different field list
is Phase 04's).

**Tech Stack:** Frappe v16.23 website pages (`www/`), Python `hmac`/`hashlib` (stdlib only — no
new dependency for HMAC-SHA512).

## Global Constraints

All constraints in [`README.md` § Global constraints](README.md#global-constraints). Sharpest
here:

- **Scoped exception to constraint §2** (verify before any DB access): this page loads the
  attempt with a read-only `frappe.db.get_value` *before* verifying, because the HMAC secret is
  per country/currency and the attempt is the only place that pairing is stored. The exception is
  bounded to this no-ledger-authority path and is recorded as ADR-0011 — it does not license
  DB-before-verify on any path that can write.
- HMAC-SHA512, `hmac.compare_digest`, never `==`.
- The page shows no amount, no transaction ID, no invoice number, no Paymob identifier.
- Every user-facing string is wrapped in `_()`, with Arabic in `translations/ar.csv` only.
- No bare `except`; the credential-lookup failure this page expects is caught by its specific
  exception type.
- `frappe.logger("paymob")` carries the Payment Request name wherever one is known.

---

## File Structure

| Path | Responsibility |
|---|---|
| `paymob_integration/paymob/hmac_verify.py` | Response-callback field list + HMAC-SHA512 verifier |
| `paymob_integration/www/__init__.py` | Makes `www` importable as `<app>.www.<page>`, per Frappe's router |
| `paymob_integration/www/paymob_result.py` | `get_context` — loads the attempt, verifies, picks the message |
| `paymob_integration/www/paymob-result.html` | The rendered page. Hyphenated to match the `/paymob-result` route |
| `paymob_integration/tests/test_hmac_verify.py` | Signature correctness, no DB |
| `paymob_integration/tests/test_result_page.py` | `get_context` behaviour against a real attempt |

**Naming note:** Frappe's router resolves a www page's controller by replacing hyphens with
underscores in the filename (`frappe/website/router.py:164` —
`page_name.replace("-", "_") + ".py"`), while the template keeps the route's own spelling. Two
existing examples in this bench confirm the pairing: `update-password.html` /
`update_password.py`, `student-portal.html` / `student_portal.py`. So the controller is
`paymob_result.py` (underscore, importable as `paymob_integration.www.paymob_result`), and the
template is `paymob-result.html` (hyphen, matching the URL). A `paymob-result.py` file — hyphen —
would silently never be found.

---

## Task 1: The response-callback HMAC verifier

**Files:**
- Create: `paymob_integration/paymob/hmac_verify.py`
- Test: `paymob_integration/tests/test_hmac_verify.py`

**Interfaces:**
- Consumes: nothing — pure functions, no DB, no network.
- Produces: `RESPONSE_CALLBACK_FIELDS: list[str]`, `verify_response_callback(params, secret) -> bool`.

- [ ] **Step 1: Write the failing test**

`paymob_integration/tests/test_hmac_verify.py`:

```python
import hashlib
import hmac as hmac_lib

from frappe.tests import UnitTestCase

from paymob_integration.paymob.hmac_verify import RESPONSE_CALLBACK_FIELDS, verify_response_callback

SECRET = "hmac_test_FAKE_secret"

VALID_PARAMS = {
	"amount_cents": "27555",
	"created_at": "2026-07-26T10:00:00.000000",
	"currency": "EGP",
	"error_occured": "false",
	"has_parent_transaction": "false",
	"id": "123456",
	"integration_id": "1234",
	"is_3d_secure": "true",
	"is_auth": "false",
	"is_capture": "false",
	"is_refunded": "false",
	"is_standalone_payment": "true",
	"is_voided": "false",
	"order": "987654",
	"owner": "5555",
	"pending": "false",
	"source_data.pan": "1234",
	"source_data.sub_type": "MasterCard",
	"source_data.type": "card",
	"success": "true",
}


def _sign(params, secret=SECRET, order_value=None):
	"""Build the same concatenation the verifier is expected to build, independently of it."""
	order_value = params.get("order", params.get("order_id", "")) if order_value is None else order_value
	values = {**params, "order": order_value}
	message = "".join(str(values.get(field, "")) for field in RESPONSE_CALLBACK_FIELDS)
	digest = hmac_lib.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()
	return {**params, "hmac": digest}


class TestVerifyResponseCallback(UnitTestCase):
	def test_valid_signature_passes(self):
		self.assertTrue(verify_response_callback(_sign(VALID_PARAMS), SECRET))

	def test_tampered_field_is_rejected(self):
		params = _sign(VALID_PARAMS)
		params["success"] = "false"  # tamper after signing
		self.assertFalse(verify_response_callback(params, SECRET))

	def test_missing_hmac_is_rejected(self):
		self.assertFalse(verify_response_callback(dict(VALID_PARAMS), SECRET))

	def test_unrelated_extra_param_is_ignored(self):
		params = _sign(VALID_PARAMS)
		params["utm_source"] = "email"
		self.assertTrue(verify_response_callback(params, SECRET))

	def test_order_id_alias_is_accepted(self):
		params = dict(VALID_PARAMS)
		del params["order"]
		params["order_id"] = "987654"
		self.assertTrue(verify_response_callback(_sign(params), SECRET))
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_hmac_verify`
Expected: FAIL — `ModuleNotFoundError: ... hmac_verify`

- [ ] **Step 3: Write the module**

`paymob_integration/paymob/hmac_verify.py`:

```python
"""Verifies Paymob's response callback (the browser redirect). Display integrity only — this
signature never gates a ledger write; the processed callback in Phase 04 has its own field list.
"""

import hashlib
import hmac

# Paymob's fixed, documented order for the response callback. A missing field reads as "" —
# dropping a field from this list changes the digest and fails closed, it never widens what
# passes.
RESPONSE_CALLBACK_FIELDS = [
	"amount_cents",
	"created_at",
	"currency",
	"error_occured",
	"has_parent_transaction",
	"id",
	"integration_id",
	"is_3d_secure",
	"is_auth",
	"is_capture",
	"is_refunded",
	"is_standalone_payment",
	"is_voided",
	"order",
	"owner",
	"pending",
	"source_data.pan",
	"source_data.sub_type",
	"source_data.type",
	"success",
]


def verify_response_callback(params, secret):
	"""True only if params["hmac"] matches HMAC-SHA512 of the fixed field order.

	`params` values are read raw — Paymob sends "true"/"false" as strings, never coerced to
	bool, because the digest is computed over the exact bytes Paymob sent.
	"""
	received = params.get("hmac")
	if not received:
		return False

	message = "".join(_read(params, field) for field in RESPONSE_CALLBACK_FIELDS)
	expected = hmac.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()
	return hmac.compare_digest(expected, received)


def _read(params, field):
	if field == "order":
		# ponytail: docs disagree whether the redirect sends `order` or `order_id`; accept
		# both until one sandbox payment settles it. DoD carries the task to record the
		# real answer in docs/reference/endpoints.md and delete the losing branch here.
		return str(params.get("order", params.get("order_id", "")))
	return str(params.get(field, ""))
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_hmac_verify`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add paymob_integration/paymob/hmac_verify.py paymob_integration/tests/test_hmac_verify.py
git commit -m "feat: verify Paymob response callback HMAC-SHA512 signatures"
```

---

## Task 2: The result page

**Files:**
- Create: `paymob_integration/www/__init__.py`
- Create: `paymob_integration/www/paymob_result.py`
- Create: `paymob_integration/www/paymob-result.html`

**Interfaces:**
- Consumes: `hmac_verify.verify_response_callback`, `paymob.settings.get_credential_set`.
- Produces: `get_context(context)` — sets `context.state` and `context.message`; module-level
  `no_cache = 1` so this page is never served stale or cached for a different attempt.

This task has no automated test of its own — `get_context` needs a real `Paymob Payment Attempt`
row to do anything meaningful, and that fixture belongs with the assertions in Task 3. Build it
here, prove it there.

- [ ] **Step 1: Create the package marker**

`paymob_integration/www/__init__.py` — empty file. Frappe imports the controller as
`<app>.www.<page>`, which requires `www` to be a package.

- [ ] **Step 2: Write the controller**

`paymob_integration/www/paymob_result.py`:

```python
"""Customer-facing result page after Paymob checkout. Renders our own stored
Paymob Payment Attempt.state — the redirect's HMAC only decides whether we trust it enough to
show that state, per ADR-0001 and ADR-0011.
"""

import frappe
from frappe import _

from paymob_integration.paymob import hmac_verify, settings

no_cache = 1

# Raw strings, not `_()`-wrapped: this dict is built once at module import, and `_()` at import
# time would freeze the translation to whichever request's language happened to trigger the
# first import in this worker. Translate at read time in get_context() instead.
MESSAGES = {
	"Pending": "We're confirming your payment.",
	"Paid": "Payment received. Thank you.",
	"Failed": "This payment did not go through. You can try again.",
	"Expired": "This payment link has expired.",
	"Refunded": "This payment has been refunded.",
}


def get_context(context):
	context.no_cache = 1
	reference = frappe.form_dict.get("merchant_order_id")
	attempt = reference and frappe.db.get_value(
		"Paymob Payment Attempt",
		reference,
		["state", "country", "currency", "payment_request"],
		as_dict=True,
	)

	if not attempt:
		frappe.logger("paymob").info("result page reason=unknown_reference")
		return _render(context, "Pending")

	state = attempt.state if _signature_is_valid(attempt) else "Pending"
	frappe.logger("paymob").info(
		f"result page shown payment_request={attempt.payment_request} state={state}"
	)
	return _render(context, state)


def _render(context, state):
	context.state = state
	context.message = _(MESSAGES.get(state, MESSAGES["Pending"]))
	return context


def _signature_is_valid(attempt):
	try:
		credentials = settings.get_credential_set(attempt.country, attempt.currency)
	except frappe.ValidationError:
		# get_credential_set throws when Paymob is disabled or the pair is unconfigured —
		# a scoped, narrow catch, not a bare except. Either way we cannot verify, so we
		# cannot trust the URL: fall back to Pending in get_context, never raise a 500.
		return False
	return hmac_verify.verify_response_callback(
		frappe.form_dict, credentials.get_password("hmac_secret")
	)
```

`context.state = "Pending"` is the security property this whole page exists to enforce: the only
thing an attacker controls is which `merchant_order_id` they point at, and the signature binds
that reference — so a tampered or unsigned URL can never render `Paid` for someone else's attempt.

- [ ] **Step 3: Write the template**

`paymob_integration/www/paymob-result.html`:

```html
{% extends "templates/web.html" %}

{% block page_content %}
<div class="paymob-result paymob-result-{{ state | lower }}">
	<h1>{{ message }}</h1>
</div>
{% endblock %}
```

`message` is already translated by `get_context`; nothing else from the attempt — no amount, no
transaction ID, no invoice number, no Paymob identifier — is ever put on `context`, so there is
nothing sensitive the template could leak even if it changed.

- [ ] **Step 4: Verify by hand**

```bash
bench build --app paymob_integration
bench --site <site> clear-cache
```

Open `https://<site>/paymob-result` with no query string at all → the neutral Pending message, no
traceback. Open it with `?merchant_order_id=does-not-exist` → same neutral page. Confirm the
response has a `Cache-Control` header preventing caching (from `no_cache`).

- [ ] **Step 5: Commit**

```bash
git add paymob_integration/www
git commit -m "feat: add the customer result page at /paymob-result"
```

---

## Task 3: Integration tests

**Files:**
- Create: `paymob_integration/tests/test_result_page.py`

**Interfaces:**
- Consumes: `paymob_integration.www.paymob_result.get_context`,
  `tests.helpers.given_submitted_payment_request`.

Calls `get_context({})` directly with `frappe.form_dict` populated — no HTTP, no network, no
webserver. Patches `settings.get_credential_set` at its binding inside the `paymob_result`
module, matching the pattern already used in
`tests/test_checkout.py`'s `TestStartCheckout.start()` (patches
`paymob_integration.api.settings.get_credential_set` at the call site, not at its definition).

- [ ] **Step 1: Write the test**

`paymob_integration/tests/test_result_page.py`:

```python
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from paymob_integration.paymob.hmac_verify import RESPONSE_CALLBACK_FIELDS
from paymob_integration.tests.helpers import given_submitted_payment_request
from paymob_integration.www import paymob_result

SECRET = "hmac_test_FAKE_secret"


def _signed_query(order_id, secret=SECRET):
	import hashlib
	import hmac as hmac_lib

	fields = {field: "" for field in RESPONSE_CALLBACK_FIELDS}
	fields.update({"order": order_id, "success": "true"})
	message = "".join(fields[field] for field in RESPONSE_CALLBACK_FIELDS)
	digest = hmac_lib.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()
	return {**fields, "merchant_order_id": order_id, "hmac": digest}


class TestResultPage(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.payment_request, self.invoice = given_submitted_payment_request()
		self.attempt = frappe.get_doc(
			{
				"doctype": "Paymob Payment Attempt",
				"special_reference": f"{self.payment_request.name}-1",
				"payment_request": self.payment_request.name,
				"state": "Paid",
				"expected_amount_cents": 27555,
				"currency": "EGP",
				"country": "Egypt",
			}
		).insert(ignore_permissions=True)
		self.credentials = Mock()
		self.credentials.get_password.return_value = SECRET

	def tearDown(self):
		frappe.delete_doc("Paymob Payment Attempt", self.attempt.name, force=True)
		self.payment_request.cancel()
		frappe.delete_doc("Payment Request", self.payment_request.name, force=True)
		self.invoice.cancel()
		frappe.delete_doc("Sales Invoice", self.invoice.name, force=True)
		frappe.db.commit()
		super().tearDown()

	def render(self, form_dict):
		frappe.form_dict.update(form_dict)
		with patch(
			"paymob_integration.www.paymob_result.settings.get_credential_set",
			return_value=self.credentials,
		):
			return paymob_result.get_context({})

	def test_paid_attempt_with_valid_signature_renders_paid(self):
		context = self.render(_signed_query(self.attempt.name))
		self.assertEqual(context.state, "Paid")

	def test_paid_attempt_with_bad_signature_renders_pending(self):
		query = _signed_query(self.attempt.name)
		query["hmac"] = "0" * 128
		context = self.render(query)
		self.assertEqual(context.state, "Pending")

	def test_unknown_reference_renders_neutral_without_raising(self):
		context = self.render({"merchant_order_id": "does-not-exist"})
		self.assertEqual(context.state, "Pending")

	def test_no_params_at_all_renders_neutral(self):
		context = paymob_result.get_context({})
		self.assertEqual(context.state, "Pending")

	def test_rendering_writes_nothing(self):
		before_modified = frappe.db.get_value("Paymob Payment Attempt", self.attempt.name, "modified")
		before_entries = frappe.db.count("Payment Entry")

		self.render(_signed_query(self.attempt.name))

		self.assertEqual(frappe.db.count("Payment Entry"), before_entries)
		self.assertEqual(
			frappe.db.get_value("Paymob Payment Attempt", self.attempt.name, "modified"),
			before_modified,
		)
```

`test_rendering_writes_nothing` is the proof, not an assumption, of "nothing on this page writes
to the ledger or changes any state" (`rules/payments.md` — money assertions count rows, "it did
not raise" proves nothing) — it checks a Payment Entry count and the attempt's own `modified`
timestamp before and after `get_context` runs.

- [ ] **Step 2: Run the tests**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_result_page`
Expected: PASS, 5 tests.

- [ ] **Step 3: Commit**

```bash
git add paymob_integration/tests/test_result_page.py
git commit -m "test: cover the result page's fail-closed HMAC verification"
```

---

## Task 4: Documentation

**Files:**
- Modify: `docs/reference/endpoints.md`, `docs/reference/decisions.md`, `docs/reference/states.md`,
  `docs/user-guide/README.md`, `paymob_integration/translations/ar.csv`

- [ ] **Step 1: Update the Response callback endpoint entry**

In `docs/reference/endpoints.md`, expand the existing `### Response callback` entry (currently
lines 32–40) so its Technical block names the real route and behaviour:

```markdown
### Response callback (browser redirect target)

**Functional:** The page the customer lands on after paying. It shows a result; it changes nothing.

**Technical:**
- Route: `GET /paymob-result?merchant_order_id=...&hmac=...` — served by
  `paymob_integration/www/paymob_result.py`, template `paymob-result.html`. `no_cache = 1`.
- `merchant_order_id` is looked up directly as the attempt's `special_reference` (its autoname).
- Loads the attempt first (read-only `frappe.db.get_value`, four columns only) to resolve the
  right per-country/currency HMAC secret, **then** verifies — the one place in the app that reads
  the database before verification, scoped by [ADR-0011](decisions.md#adr-0011--the-result-page-resolves-the-credential-set-before-verifying-the-redirect-signature).
- Auth: verify HMAC-SHA512 for display integrity only; **never** write the ledger from here.
- Side effects: none. Renders a **generic** result page; the two channels (this and the processed
  callback) can race, so `Pending` is always a correct answer.
- Fails closed: unknown reference, unconfigured credentials, or a bad/missing signature all
  render the same neutral **Pending** page, never a 404 or 500.
- Ledger authority: **no**.
```

- [ ] **Step 2: Add a named error path**

In `docs/reference/endpoints.md` § Named error paths, add a new entry directly after
`### HMAC verification failure` (around line 76) — it is a **different** answer for a different
channel, not a restatement:

```markdown
### Response callback signature failure

**Functional:** A customer whose result-page link was tampered with sees "we're confirming your
payment," never a fake "paid" or "failed."

**Technical:** Unlike the processed callback (which rejects with a `401`), the response callback
still returns `200` and renders the neutral `Pending` message — refusing outright would just be a
worse UX for a page with no ledger authority to protect. Logs `reason=unknown_reference` or
relies on the credential lookup's own narrow exception; never echoes the attacker-supplied
`merchant_order_id` back into the log line.
```

- [ ] **Step 3: Add ADR-0011**

Append to `docs/reference/decisions.md` (next free number after 0001–0003, 0010, 0004):

```markdown
### ADR-0011 — The result page resolves the credential set before verifying the redirect signature

**Date:** 2026-07-26 · **Status:** Accepted

**Functional:** The result page can find the right secret to check, for every country Paymob
accounts are configured in, without guessing.

**Technical:**
- **Context:** `rules/implementation-gate.md` §2 requires verification before any database
  access. But the HMAC secret is stored per country/currency on `Paymob Credential Set`, and the
  only place that pairing is recorded for a given checkout is the `Paymob Payment Attempt` row
  itself — there is no way to pick the right secret without a lookup first.
- **Decision:** Load the attempt with a read-only `frappe.db.get_value` (four non-sensitive
  columns, no `get_doc`, no `client_secret`), resolve its credential set, then verify.
  The alternative — trial-verifying the signature against every enabled credential set until one
  matches — still reads the database (every row instead of one) and adds branching for no
  security benefit, since a wrong-secret trial and a genuine forgery look identical either way.
- **Consequences / why:** the exception is bounded to this page, which has no ledger authority
  (ADR-0001) and performs no write in any branch. It does not license "load then verify" on any
  path that can move money — those paths still verify strictly first, per gate §2.
```

- [ ] **Step 4: Update states.md with the customer-visible sentence**

`docs/reference/states.md` already gives `pending` its customer sentence ("The customer sees
'We're confirming your payment.'"). Add the matching sentence to the Functional line of `paid`,
`failed`, `expired`, and `refunded`:

| State | Append to Functional line |
|---|---|
| `paid` | The customer sees "Payment received. Thank you." |
| `failed` | The customer sees "This payment did not go through. You can try again." |
| `expired` | The customer sees "This payment link has expired." |
| `refunded` | The customer sees "This payment has been refunded." |

No new states — the DocType's five Select options already cover every message this page renders.

- [ ] **Step 5: Add the Arabic strings**

Append to `paymob_integration/translations/ar.csv` (currently 48 lines, unquoted `source,arabic`):

```csv
We're confirming your payment.,نقوم بتأكيد عملية الدفع الخاصة بك.
Payment received. Thank you.,تم استلام الدفعة. شكرًا لك.
This payment did not go through. You can try again.,لم تكتمل عملية الدفع. يمكنك المحاولة مرة أخرى.
This payment link has expired.,انتهت صلاحية رابط الدفع هذا.
This payment has been refunded.,تم استرداد هذه الدفعة.
```

- [ ] **Step 6: Write the merchant-facing note**

Add a short section to `docs/user-guide/README.md` explaining what the customer sees at
`/paymob-result` and why: the page can say "we're confirming your payment" even when the payment
already succeeded, because the real confirmation travels server-to-server and can arrive slightly
before or after the customer's browser redirect (ADR-0001) — this is not a stall or a bug, and no
merchant action is needed while it resolves.

- [ ] **Step 7: Commit**

```bash
git add docs paymob_integration/translations/ar.csv
git commit -m "docs: document the result page, ADR-0011, and its states"
```

---

## Definition of Done

- [ ] `bench --site <site> run-tests --module paymob_integration.tests.test_hmac_verify` passes.
- [ ] `bench --site <site> run-tests --module paymob_integration.tests.test_result_page` passes.
- [ ] Nothing on this path writes — proven by `test_rendering_writes_nothing`'s Payment Entry
      count and `modified`-timestamp assertions, not by inspection.
- [ ] A tampered or missing signature never renders `Paid`, `Failed`, `Expired`, or `Refunded` —
      only ever the neutral `Pending` page.
- [ ] The page exposes no amount, transaction ID, invoice number, or Paymob identifier —
      `get_context` reads only `state`, `country`, `currency`, `payment_request` from the DB.
- [ ] An unknown or missing `merchant_order_id` renders the neutral page; no 404, no 500.
- [ ] Both channels racing (webhook and redirect arriving in either order) leaves `Pending` as a
      correct, non-alarming answer.
- [ ] `www/paymob_result.py` (underscore) and `www/paymob-result.html` (hyphen) are named per
      Frappe's router convention, not both hyphenated.
- [ ] No test makes a network call.
- [ ] Run one sandbox payment, capture the redirect query string, record whether Paymob sends
      `order` or `order_id` in `endpoints.md`, and **delete the losing branch** in
      `hmac_verify._read()`.
- [ ] New strings are translated and present in `ar.csv`.
- [ ] `endpoints.md`, `decisions.md`, `states.md`, and the user guide are updated.
- [ ] `bench --site <site> run-tests --app paymob_integration` passes.
- [ ] `pre-commit run --all-files` passes.
