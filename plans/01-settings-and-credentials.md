# Phase 01 — Settings & Credentials Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** A merchant can store per-country Paymob credentials encrypted, and prove they work by
clicking **Test Connection**, which obtains a real auth token from Paymob.

**Architecture:** One Single doctype (`Paymob Settings`) holding two child tables — credential
sets keyed by country/currency/mode, and integration IDs keyed the same way. All outbound HTTP
goes through one client module that always sets a timeout and translates network failures into
two named exceptions. The auth token (API key → Bearer token, needed later by Transaction
Inquiry) is fetched here and cached, because Test Connection is exactly the call that proves the
API key is right.

**Tech Stack:** Frappe v16.23, ERPNext v16.23, Python 3.14, `requests` (bundled with Frappe),
`frappe.tests.UnitTestCase` / `IntegrationTestCase`.

## Global Constraints

All constraints in [`README.md` § Global constraints](README.md#global-constraints) apply. The
ones this phase exercises hardest:

- Credentials use the **Password** fieldtype, read with `get_password()`. Never `Data`.
- Test fixtures use obviously fake values (`sk_test_FAKE_...`). No real credential, not even a
  test-mode one.
- Only the **public key** may reach the browser.
- Every outbound call sets a `timeout` and handles connection errors explicitly.
- No test makes a network call — `requests.request` is patched.
- Tabs for indentation, double quotes, `pre-commit run --all-files` passes.

---

## File Structure

| Path | Responsibility |
|---|---|
| `paymob_integration/paymob/__init__.py` | Package marker for the gateway logic modules |
| `paymob_integration/paymob/client.py` | The only place `requests` is called. Timeouts, named exceptions |
| `paymob_integration/paymob/settings.py` | Reads `Paymob Settings`, resolves a credential set and integration IDs |
| `paymob_integration/paymob/auth.py` | API key → Bearer auth token, with cache and forced refresh |
| `paymob_integration/paymob_integration/doctype/paymob_credential_set/` | Child table: one country's keys |
| `paymob_integration/paymob_integration/doctype/paymob_integration_id/` | Child table: one payment method's integration ID |
| `paymob_integration/paymob_integration/doctype/paymob_settings/` | Single doctype + `test_connection` method |
| `paymob_integration/tests/__init__.py` | Test package marker |
| `paymob_integration/tests/fixtures.py` | Fake credential builder shared by every later phase |
| `paymob_integration/tests/test_client.py` | Timeout and error translation |
| `paymob_integration/tests/test_settings.py` | Credential resolution rules |
| `paymob_integration/tests/test_auth.py` | Token fetch, cache, forced refresh |
| `paymob_integration/translations/ar.csv` | Arabic for every string added in this phase |

---

## Task 1: The HTTP client

**Files:**
- Create: `paymob_integration/paymob/__init__.py`
- Create: `paymob_integration/paymob/client.py`
- Create: `paymob_integration/tests/__init__.py`
- Test: `paymob_integration/tests/test_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `PaymobError`, `PaymobNetworkError`, `PaymobAPIError(status_code)`,
  `request(method, url, *, headers=None, json_body=None, timeout=30) -> dict`.

- [ ] **Step 1: Create the empty packages**

```bash
mkdir -p paymob_integration/paymob paymob_integration/tests
touch paymob_integration/paymob/__init__.py paymob_integration/tests/__init__.py
```

- [ ] **Step 2: Write the failing test**

`paymob_integration/tests/test_client.py`:

```python
from unittest.mock import patch

import requests
from frappe.tests import UnitTestCase

from paymob_integration.paymob import client


class TestPaymobClient(UnitTestCase):
	def test_timeout_is_always_set(self):
		with patch("paymob_integration.paymob.client.requests.request") as mocked:
			mocked.return_value.status_code = 200
			mocked.return_value.json.return_value = {"ok": True}
			client.request("GET", "https://example.test/ping")

		self.assertEqual(mocked.call_args.kwargs["timeout"], client.DEFAULT_TIMEOUT)

	def test_timeout_becomes_network_error(self):
		with patch(
			"paymob_integration.paymob.client.requests.request",
			side_effect=requests.Timeout("too slow"),
		):
			with self.assertRaises(client.PaymobNetworkError):
				client.request("GET", "https://example.test/ping")

	def test_connection_failure_becomes_network_error(self):
		with patch(
			"paymob_integration.paymob.client.requests.request",
			side_effect=requests.ConnectionError("no route"),
		):
			with self.assertRaises(client.PaymobNetworkError):
				client.request("GET", "https://example.test/ping")

	def test_http_error_carries_status_code_and_not_the_body(self):
		with patch("paymob_integration.paymob.client.requests.request") as mocked:
			mocked.return_value.status_code = 401
			mocked.return_value.text = "sk_test_FAKE_leaked_in_body"

			with self.assertRaises(client.PaymobAPIError) as caught:
				client.request("POST", "https://example.test/auth")

		self.assertEqual(caught.exception.status_code, 401)
		self.assertNotIn("sk_test_FAKE", str(caught.exception))
```

- [ ] **Step 3: Run the test and watch it fail**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_client`
Expected: FAIL — `ModuleNotFoundError: No module named 'paymob_integration.paymob.client'`

- [ ] **Step 4: Write the client**

`paymob_integration/paymob/client.py`:

```python
"""The only module that talks to the network. Every Paymob call goes through request()."""

import frappe
import requests
from frappe import _

DEFAULT_TIMEOUT = 30


class PaymobError(frappe.ValidationError):
	"""Base class for every Paymob failure."""


class PaymobNetworkError(PaymobError):
	"""We never reached Paymob, or never heard back. Says nothing about the money."""


class PaymobAPIError(PaymobError):
	"""Paymob answered with a non-2xx status."""

	def __init__(self, message, status_code=None):
		super().__init__(message)
		self.status_code = status_code


def request(method, url, *, headers=None, json_body=None, timeout=DEFAULT_TIMEOUT):
	"""Call Paymob and return the decoded JSON body.

	Raises PaymobNetworkError when Paymob could not be reached, PaymobAPIError when it
	answered with an error status. The response body is never put in the exception message:
	Paymob echoes request fields, and a request can carry a credential.
	"""
	try:
		response = requests.request(
			method, url, headers=headers, json=json_body, timeout=timeout
		)
	except requests.Timeout as exc:
		raise PaymobNetworkError(
			_("Paymob did not answer in time. The payment has not changed. Please try again.")
		) from exc
	except requests.RequestException as exc:
		raise PaymobNetworkError(
			_("Could not reach Paymob. The payment has not changed. Please try again.")
		) from exc

	if response.status_code >= 400:
		raise PaymobAPIError(
			f"Paymob returned HTTP {response.status_code} for {method} {url}",
			status_code=response.status_code,
		)

	return response.json()
```

- [ ] **Step 5: Run the test and watch it pass**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_client`
Expected: PASS, 4 tests.

- [ ] **Step 6: Add the Arabic strings**

`paymob_integration/translations/ar.csv` (create the folder and file):

```csv
Paymob did not answer in time. The payment has not changed. Please try again.,لم يستجب باي موب في الوقت المحدد. لم تتغير حالة الدفع. برجاء المحاولة مرة أخرى.
Could not reach Paymob. The payment has not changed. Please try again.,تعذر الاتصال بباي موب. لم تتغير حالة الدفع. برجاء المحاولة مرة أخرى.
```

- [ ] **Step 7: Commit**

```bash
git add paymob_integration/paymob paymob_integration/tests paymob_integration/translations
git commit -m "feat: add Paymob HTTP client with mandatory timeouts"
```

---

## Task 2: The Settings doctype and its child tables

**Files:**
- Create: `paymob_integration/paymob_integration/doctype/paymob_credential_set/paymob_credential_set.json`
- Create: `paymob_integration/paymob_integration/doctype/paymob_credential_set/paymob_credential_set.py`
- Create: `paymob_integration/paymob_integration/doctype/paymob_integration_id/paymob_integration_id.json`
- Create: `paymob_integration/paymob_integration/doctype/paymob_integration_id/paymob_integration_id.py`
- Create: `paymob_integration/paymob_integration/doctype/paymob_settings/paymob_settings.json`
- Create: `paymob_integration/paymob_integration/doctype/paymob_settings/paymob_settings.py`

**Interfaces:**
- Consumes: nothing.
- Produces: DocTypes `Paymob Settings` (Single), `Paymob Credential Set` (child),
  `Paymob Integration ID` (child). Field names are relied on by every later phase.

- [ ] **Step 1: Create the doctypes through the UI, then export**

DocTypes are created on a site and their JSON committed — never hand-written
(`rules/frappe-discipline.md`). Open the site as Administrator and create:

**`Paymob Credential Set`** — Is Child Table: yes, Module: Paymob Integration.

| Fieldname | Type | Notes |
|---|---|---|
| `enabled` | Check | default `1`, In List View |
| `country` | Data | reqd, In List View. e.g. `Egypt` |
| `currency` | Link → Currency | reqd, In List View |
| `mode` | Select | options `Test\nLive`, reqd, In List View, default `Test` |
| `base_url` | Data | reqd. e.g. `https://accept.paymob.com` |
| `public_key` | Data | reqd. The only credential allowed in a browser |
| `secret_key` | **Password** | reqd |
| `api_key` | **Password** | reqd |
| `hmac_secret` | **Password** | reqd |
| `payment_account` | Link → Account | reqd. The clearing/bank account money lands in |

**`Paymob Integration ID`** — Is Child Table: yes.

| Fieldname | Type | Notes |
|---|---|---|
| `enabled` | Check | default `1`, In List View |
| `country` | Data | reqd, In List View |
| `currency` | Link → Currency | reqd, In List View |
| `mode` | Select | options `Test\nLive`, reqd |
| `payment_method` | Data | reqd, In List View. e.g. `Card`, `Wallet` |
| `integration_id` | Data | reqd |

**`Paymob Settings`** — Is Single: yes, Module: Paymob Integration.

| Fieldname | Type | Notes |
|---|---|---|
| `enabled` | Check | default `0` |
| `mode` | Select | options `Test\nLive`, reqd, default `Test` |
| `credential_sets` | Table → Paymob Credential Set | |
| `integration_ids` | Table → Paymob Integration ID | |
| `intention_expiration_seconds` | Int | default `3600` |
| `stale_pending_minutes` | Int | default `20`. How old a pending attempt must be before the poller looks at it |

Permissions on `Paymob Settings`: **System Manager** read/write. No other role. Nobody reads a
Password field through the API regardless of role — that is Frappe's own protection.

- [ ] **Step 2: Export the JSON into the app**

```bash
bench --site <site> export-fixtures --app paymob_integration
bench --site <site> migrate
git status --short paymob_integration/paymob_integration/doctype
```

Expected: three new doctype folders, each with `.json`, `.py`, `__init__.py`.

- [ ] **Step 3: Verify the Password fields really are encrypted**

Run: `bench --site <site> console`

```python
import json
d = json.load(open("apps/paymob_integration/paymob_integration/paymob_integration/doctype/paymob_credential_set/paymob_credential_set.json"))
print([f["fieldname"] for f in d["fields"] if f["fieldtype"] == "Password"])
```

Expected: `['secret_key', 'api_key', 'hmac_secret']`. If `public_key` appears in that list, or
any of those three does not, fix the doctype and re-export. This is the check that stops the
single most expensive mistake in the app.

- [ ] **Step 4: Commit**

```bash
git add paymob_integration/paymob_integration/doctype
git commit -m "feat: add Paymob Settings with per-country encrypted credential sets"
```

---

## Task 3: Resolving a credential set

**Files:**
- Create: `paymob_integration/paymob/settings.py`
- Create: `paymob_integration/tests/fixtures.py`
- Test: `paymob_integration/tests/test_settings.py`

**Interfaces:**
- Consumes: `Paymob Settings` doctype from Task 2.
- Produces:
  - `get_settings() -> Document`
  - `get_credential_set(currency: str) -> Document` — the child row; raises `frappe.ValidationError` when none matches
  - `get_integration_ids(currency: str) -> list[str]`
  - `base_url(credentials) -> str` — trailing slash stripped

- [ ] **Step 1: Write the shared test fixture**

`paymob_integration/tests/fixtures.py`:

```python
"""Fake Paymob configuration for tests. Every value here is deliberately not a credential."""

import frappe

FAKE_SECRET_KEY = "sk_test_FAKE_secret"
FAKE_API_KEY = "api_test_FAKE_key"
FAKE_HMAC_SECRET = "FAKE_HMAC_SECRET"
FAKE_PUBLIC_KEY = "pk_test_FAKE_public"
FAKE_BASE_URL = "https://accept.paymob.test"


def given_paymob_settings(mode="Test", currency="EGP", payment_account=None):
	"""Configure Paymob Settings with one enabled credential set and one integration ID."""
	settings = frappe.get_single("Paymob Settings")
	settings.enabled = 1
	settings.mode = mode
	settings.intention_expiration_seconds = 3600
	settings.stale_pending_minutes = 20
	settings.credential_sets = []
	settings.integration_ids = []
	settings.append(
		"credential_sets",
		{
			"enabled": 1,
			"country": "Egypt",
			"currency": currency,
			"mode": mode,
			"base_url": FAKE_BASE_URL,
			"public_key": FAKE_PUBLIC_KEY,
			"secret_key": FAKE_SECRET_KEY,
			"api_key": FAKE_API_KEY,
			"hmac_secret": FAKE_HMAC_SECRET,
			"payment_account": payment_account or _any_bank_account(),
		},
	)
	settings.append(
		"integration_ids",
		{
			"enabled": 1,
			"country": "Egypt",
			"currency": currency,
			"mode": mode,
			"payment_method": "Card",
			"integration_id": "1234567",
		},
	)
	settings.save()
	frappe.clear_cache(doctype="Paymob Settings")
	return settings


def _any_bank_account():
	return frappe.db.get_value("Account", {"account_type": "Bank", "is_group": 0}, "name")
```

- [ ] **Step 2: Write the failing test**

`paymob_integration/tests/test_settings.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from paymob_integration.paymob import settings
from paymob_integration.tests.fixtures import FAKE_SECRET_KEY, given_paymob_settings


class TestCredentialResolution(IntegrationTestCase):
	def test_returns_the_row_matching_currency_and_mode(self):
		given_paymob_settings(mode="Test", currency="EGP")

		credentials = settings.get_credential_set("EGP")

		self.assertEqual(credentials.country, "Egypt")
		self.assertEqual(credentials.mode, "Test")

	def test_secrets_come_back_decrypted_only_through_get_password(self):
		given_paymob_settings()

		credentials = settings.get_credential_set("EGP")

		self.assertEqual(credentials.get_password("secret_key"), FAKE_SECRET_KEY)
		self.assertNotEqual(credentials.secret_key, FAKE_SECRET_KEY)

	def test_unknown_currency_is_refused(self):
		given_paymob_settings(currency="EGP")

		with self.assertRaises(frappe.ValidationError):
			settings.get_credential_set("USD")

	def test_live_mode_never_falls_back_to_a_test_credential_set(self):
		given_paymob_settings(mode="Test", currency="EGP")
		single = frappe.get_single("Paymob Settings")
		single.mode = "Live"
		single.save()
		frappe.clear_cache(doctype="Paymob Settings")

		with self.assertRaises(frappe.ValidationError):
			settings.get_credential_set("EGP")

	def test_disabled_integration_ids_are_not_offered(self):
		given_paymob_settings()
		single = frappe.get_single("Paymob Settings")
		single.integration_ids[0].enabled = 0
		single.save()
		frappe.clear_cache(doctype="Paymob Settings")

		self.assertEqual(settings.get_integration_ids("EGP"), [])
```

The fourth test is the important one. A "helpful" fallback to the test credential set when the
live one is missing is how test keys end up serving production traffic.

- [ ] **Step 3: Run the test and watch it fail**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_settings`
Expected: FAIL — `AttributeError: module ... has no attribute 'get_credential_set'`

- [ ] **Step 4: Write the resolver**

`paymob_integration/paymob/settings.py`:

```python
"""Reads Paymob Settings. No other module opens that doctype directly."""

import frappe
from frappe import _


def get_settings():
	return frappe.get_cached_doc("Paymob Settings")


def get_credential_set(currency):
	"""Return the enabled credential set for this currency in the site's current mode.

	There is deliberately no fallback. A missing Live credential set is an error, not an
	invitation to use the Test one.
	"""
	config = get_settings()
	if not config.enabled:
		frappe.throw(_("Paymob is not enabled. Ask an administrator to configure Paymob Settings."))

	for row in config.credential_sets:
		if row.enabled and row.currency == currency and row.mode == config.mode:
			return row

	frappe.throw(
		_("No Paymob credentials are configured for currency {0} in {1} mode.").format(
			currency, config.mode
		)
	)


def get_integration_ids(currency):
	"""Return the integration IDs offered at checkout for this currency and mode."""
	config = get_settings()
	return [
		row.integration_id
		for row in config.integration_ids
		if row.enabled and row.currency == currency and row.mode == config.mode
	]


def base_url(credentials):
	return credentials.base_url.rstrip("/")
```

Note the `.format()` call: the whole sentence is translated once and the values are passed in,
because Arabic puts them in a different place (`rules/translation.md`).

- [ ] **Step 5: Run the test and watch it pass**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_settings`
Expected: PASS, 5 tests.

- [ ] **Step 6: Add the Arabic strings**

Append to `paymob_integration/translations/ar.csv`:

```csv
Paymob is not enabled. Ask an administrator to configure Paymob Settings.,باي موب غير مفعل. برجاء الطلب من المسؤول ضبط إعدادات باي موب.
No Paymob credentials are configured for currency {0} in {1} mode.,لا توجد بيانات اعتماد لباي موب للعملة {0} في وضع {1}.
```

- [ ] **Step 7: Commit**

```bash
git add paymob_integration/paymob/settings.py paymob_integration/tests paymob_integration/translations
git commit -m "feat: resolve Paymob credentials by currency and mode with no fallback"
```

---

## Task 4: The auth token

**Files:**
- Create: `paymob_integration/paymob/auth.py`
- Test: `paymob_integration/tests/test_auth.py`

**Interfaces:**
- Consumes: `client.request`, `settings.base_url`.
- Produces: `get_auth_token(credentials, force_refresh: bool = False) -> str`, cached under
  `paymob_auth_token:<country>:<mode>` for `TOKEN_TTL_SECONDS`.

Phase 10's poller depends on this. It is built here because Test Connection is the honest way to
prove an API key works, and that is the same call.

- [ ] **Step 1: Write the failing test**

`paymob_integration/tests/test_auth.py`:

```python
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from paymob_integration.paymob import auth, settings
from paymob_integration.tests.fixtures import FAKE_API_KEY, given_paymob_settings


class TestAuthToken(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		given_paymob_settings()
		self.credentials = settings.get_credential_set("EGP")
		frappe.cache().delete_value(auth.cache_key(self.credentials))

	def test_posts_the_api_key_and_returns_the_token(self):
		with patch(
			"paymob_integration.paymob.auth.client.request",
			return_value={"token": "tok_FAKE_1"},
		) as mocked:
			token = auth.get_auth_token(self.credentials)

		self.assertEqual(token, "tok_FAKE_1")
		self.assertEqual(mocked.call_args.kwargs["json_body"], {"api_key": FAKE_API_KEY})

	def test_second_call_uses_the_cache(self):
		with patch(
			"paymob_integration.paymob.auth.client.request",
			return_value={"token": "tok_FAKE_1"},
		) as mocked:
			auth.get_auth_token(self.credentials)
			auth.get_auth_token(self.credentials)

		self.assertEqual(mocked.call_count, 1)

	def test_force_refresh_ignores_the_cache(self):
		with patch(
			"paymob_integration.paymob.auth.client.request",
			side_effect=[{"token": "tok_FAKE_1"}, {"token": "tok_FAKE_2"}],
		) as mocked:
			auth.get_auth_token(self.credentials)
			token = auth.get_auth_token(self.credentials, force_refresh=True)

		self.assertEqual(mocked.call_count, 2)
		self.assertEqual(token, "tok_FAKE_2")
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_auth`
Expected: FAIL — `ModuleNotFoundError: No module named 'paymob_integration.paymob.auth'`

- [ ] **Step 3: Write the auth module**

`paymob_integration/paymob/auth.py`:

```python
"""API key -> Bearer auth token, used by Transaction Inquiry.

The token's real lifetime is not documented by Paymob. We cache it for less than the value
folklore reports and always handle a 401 by refreshing once, so the cache TTL being wrong
costs one extra request and never costs correctness.
"""

import frappe

from paymob_integration.paymob import client, settings

TOKEN_TTL_SECONDS = 45 * 60


def cache_key(credentials):
	return f"paymob_auth_token:{credentials.country}:{credentials.mode}"


def get_auth_token(credentials, force_refresh=False):
	key = cache_key(credentials)
	if not force_refresh:
		cached = frappe.cache().get_value(key)
		if cached:
			return cached

	response = client.request(
		"POST",
		f"{settings.base_url(credentials)}/api/auth/tokens",
		json_body={"api_key": credentials.get_password("api_key")},
	)
	token = response["token"]
	frappe.cache().set_value(key, token, expires_in_sec=TOKEN_TTL_SECONDS)
	return token
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_auth`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add paymob_integration/paymob/auth.py paymob_integration/tests/test_auth.py
git commit -m "feat: obtain and cache the Paymob auth token"
```

---

## Task 5: The Test Connection button

**Files:**
- Modify: `paymob_integration/paymob_integration/doctype/paymob_settings/paymob_settings.py`
- Create: `paymob_integration/paymob_integration/doctype/paymob_settings/paymob_settings.js`
- Test: `paymob_integration/tests/test_settings.py` (append a class)

**Interfaces:**
- Consumes: `auth.get_auth_token`, `settings.get_credential_set`.
- Produces: whitelisted `paymob_integration.paymob_integration.doctype.paymob_settings.paymob_settings.test_connection(currency)`.

- [ ] **Step 1: Write the failing test**

Append to `paymob_integration/tests/test_settings.py`:

```python
from unittest.mock import patch

from paymob_integration.paymob_integration.doctype.paymob_settings import paymob_settings
from paymob_integration.tests.fixtures import given_paymob_settings


class TestConnectionCheck(IntegrationTestCase):
	def test_reports_success_when_paymob_issues_a_token(self):
		given_paymob_settings()

		with patch(
			"paymob_integration.paymob.auth.client.request",
			return_value={"token": "tok_FAKE_1"},
		):
			result = paymob_settings.test_connection("EGP")

		self.assertTrue(result["ok"])

	def test_the_token_never_appears_in_the_result(self):
		given_paymob_settings()

		with patch(
			"paymob_integration.paymob.auth.client.request",
			return_value={"token": "tok_FAKE_1"},
		):
			result = paymob_settings.test_connection("EGP")

		self.assertNotIn("tok_FAKE_1", frappe.as_json(result))

	def test_a_non_system_manager_is_refused(self):
		given_paymob_settings()
		frappe.set_user(self.make_plain_user())

		with self.assertRaises(frappe.PermissionError):
			paymob_settings.test_connection("EGP")

		frappe.set_user("Administrator")

	def make_plain_user(self):
		email = "paymob-plain-user@example.test"
		if not frappe.db.exists("User", email):
			user = frappe.new_doc("User")
			user.email = email
			user.first_name = "Plain"
			user.append("roles", {"role": "Sales User"})
			user.insert(ignore_permissions=True)
		return email
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_settings`
Expected: FAIL — `AttributeError: module ... has no attribute 'test_connection'`

- [ ] **Step 3: Write the method**

`paymob_integration/paymob_integration/doctype/paymob_settings/paymob_settings.py`:

```python
import frappe
from frappe import _
from frappe.model.document import Document

from paymob_integration.paymob import auth, settings


class PaymobSettings(Document):
	pass


@frappe.whitelist()
def test_connection(currency):
	"""Prove the configured API key authenticates against Paymob.

	Reads nothing from the caller except the currency, and returns no credential material.
	"""
	frappe.only_for("System Manager")

	credentials = settings.get_credential_set(currency)
	auth.get_auth_token(credentials, force_refresh=True)

	frappe.logger("paymob").info(
		f"test_connection ok country={credentials.country} mode={credentials.mode}"
	)
	return {
		"ok": True,
		"message": _("Connected to Paymob for {0} in {1} mode.").format(
			credentials.country, credentials.mode
		),
	}
```

`frappe.only_for` raises `frappe.PermissionError`, which is what the test asserts. The returned
dict carries a message and a boolean — never the token, never the country's keys.

- [ ] **Step 4: Write the button**

`paymob_integration/paymob_integration/doctype/paymob_settings/paymob_settings.js`:

```javascript
frappe.ui.form.on("Paymob Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.prompt(
				{
					fieldname: "currency",
					fieldtype: "Link",
					options: "Currency",
					label: __("Currency"),
					reqd: 1,
				},
				({ currency }) => {
					frappe.call({
						method:
							"paymob_integration.paymob_integration.doctype.paymob_settings.paymob_settings.test_connection",
						args: { currency },
						freeze: true,
						freeze_message: __("Contacting Paymob..."),
						callback: ({ message }) => {
							frappe.msgprint({
								title: __("Paymob"),
								message: message.message,
								indicator: "green",
							});
						},
					});
				},
				__("Test Connection"),
				__("Test")
			);
		});
	},
});
```

- [ ] **Step 5: Run the test and watch it pass**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_settings`
Expected: PASS, 8 tests.

- [ ] **Step 6: Try it by hand against real Paymob test credentials**

Put real **test-mode** credentials into Paymob Settings on your development site, click
**Test Connection**, and confirm the green message. Then change one character of the API key and
confirm you get an error message with no traceback and no key echoed back.

Do not commit those credentials. Run `git status` and confirm nothing under
`sites/` is staged.

- [ ] **Step 7: Add the Arabic strings**

Append to `paymob_integration/translations/ar.csv`:

```csv
Connected to Paymob for {0} in {1} mode.,تم الاتصال بباي موب لـ {0} في وضع {1}.
Test Connection,اختبار الاتصال
Contacting Paymob...,جارٍ الاتصال بباي موب...
Currency,العملة
Paymob,باي موب
Test,اختبار
```

- [ ] **Step 8: Commit**

```bash
git add paymob_integration/paymob_integration/doctype/paymob_settings paymob_integration/tests paymob_integration/translations
git commit -m "feat: add Test Connection to Paymob Settings"
```

---

## Task 6: Documentation

**Files:**
- Modify: `docs/reference/endpoints.md`
- Modify: `docs/reference/fields.md`
- Modify: `docs/reference/decisions.md`
- Modify: `docs/user-guide/README.md`

- [ ] **Step 1: Document the settings**

Replace the "Credential storage" entry in `docs/reference/endpoints.md` § Settings with the real
shape, keeping the two-lens format:

```markdown
### Paymob Settings (Single)

**Functional:** One place where a merchant enters their Paymob account details, one set per
country they sell in, and switches the whole site between test and live.

**Technical:**
- `enabled` gates every outbound call. `mode` (`Test`/`Live`) selects which credential rows are
  live; there is **no fallback** from Live to Test — a missing Live row raises an error.
- `credential_sets` (child `Paymob Credential Set`): country, currency, mode, base URL,
  `public_key` (Data — browser-safe), `secret_key`/`api_key`/`hmac_secret` (**Password**,
  encrypted at rest, read only through `get_password()`), and `payment_account` — the clearing
  account payments land in.
- `integration_ids` (child `Paymob Integration ID`): the payment methods offered at checkout,
  keyed by country/currency/mode. A mode mismatch here fails at checkout, not at save time.
- `intention_expiration_seconds` (default 3600) and `stale_pending_minutes` (default 20) drive
  intention expiry and the reconciliation poller.
- Permission: System Manager only.

### Test Connection

**Functional:** A button that proves the saved keys work before any customer relies on them.

**Technical:**
- Whitelisted method, `frappe.only_for("System Manager")`.
- Calls `POST {base_url}/api/auth/tokens` with the API key and discards the token.
- Returns `{ok, message}` — never the token, never a key.
- Ledger authority: none.
```

- [ ] **Step 2: Document the fields**

Append to `docs/reference/fields.md`, two lenses each: `mode`, `payment_account`,
`intention_expiration_seconds`, `stale_pending_minutes`, and one entry covering the three
Password credentials (source of truth: the Paymob dashboard; mutability: replaced on rotation;
validation: proven by Test Connection, never by save).

- [ ] **Step 3: Write ADR-0010**

Append to `docs/reference/decisions.md`:

```markdown
### ADR-0010 — The `payments` app is not a dependency

**Date:** <today> · **Status:** Accepted

**Functional:** Installing this app does not require installing another one.

**Technical:**
- **Context:** ERPNext's Payment Request has gateway machinery (`get_payment_url`,
  `on_payment_authorized`) that resolves a controller through the `Payment Gateway` doctype.
  That doctype lives in the separate `payments` app, which is not installed on this bench.
- **Decision:** Drive the Payment Request directly. Paymob configuration lives in our own
  `Paymob Settings`, and the clearing account is `Paymob Credential Set.payment_account`
  rather than a Payment Gateway Account.
- **Consequences / why:** one fewer dependency and one fewer indirection to review. The cost is
  that we do not inherit `payments`' gateway UI; the **Pay with Paymob** button (Phase 02) is
  ours. If `payments` is installed later, nothing here conflicts with it.
```

- [ ] **Step 4: Write the merchant setup section**

Add to `docs/user-guide/README.md`: where to find Paymob Settings, which four values to copy
from which Paymob dashboard page, why test and live rows both exist, and that **Test Connection
must be green before going further**. No screenshots containing keys.

- [ ] **Step 5: Commit**

```bash
git add docs
git commit -m "docs: document Paymob Settings, Test Connection, and ADR-0010"
```

---

## Definition of Done

- [ ] A merchant can save credentials for at least two countries and both modes.
- [ ] `secret_key`, `api_key`, `hmac_secret` are Password fields; `public_key` is not.
- [ ] Test Connection returns green with valid keys and a clean, translated error with bad ones.
- [ ] No credential appears in any log line, in the returned payload, or in the diff.
- [ ] Live mode never falls back to a Test credential set — proven by a test.
- [ ] Every outbound call goes through `client.request` and has a timeout — proven by a test.
- [ ] No test makes a network call.
- [ ] Every new user-facing string is in `_()`/`__()` and has an Arabic row in `ar.csv`.
- [ ] `docs/reference/endpoints.md`, `fields.md`, `decisions.md` and the user guide are updated.
- [ ] `bench --site <site> run-tests --app paymob_integration` passes.
- [ ] `pre-commit run --all-files` passes, including the secret scan.
