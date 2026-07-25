# Phase 02 — Intention & Checkout URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** From a submitted Payment Request, a user clicks **Pay with Paymob** and receives a
hosted-checkout URL. Every identifier needed to match the eventual callback is already stored in
the database before that URL is handed out.

**Architecture:** A new `Paymob Payment Attempt` doctype owns the payment lifecycle. It is
created **first**, reserving a unique `special_reference`, then the intention is created at
Paymob, then the returned identifiers are written back. A retry is a new attempt, never a reset
of the old one. The amount is converted to integer minor units once, at this moment, and frozen.

**Tech Stack:** Frappe v16.23, ERPNext v16.23 (`Payment Request`), Python `decimal`.

## Global Constraints

All constraints in [`README.md` § Global constraints](README.md#global-constraints). Sharpest
here:

- Money is integer cents. `Decimal`, never `float`.
- The expected amount is read from the **database**, never from the request body.
- Every whitelisted method checks permission on the document first.
- A network failure never changes payment state.
- Identifiers are persisted **before** the customer is redirected.

---

## File Structure

| Path | Responsibility |
|---|---|
| `paymob_integration/paymob/amounts.py` | Currency → minor units. The only place money changes representation |
| `paymob_integration/paymob/intention.py` | Builds and sends the Intention API request |
| `paymob_integration/paymob_integration/doctype/paymob_payment_attempt/` | Lifecycle record: one row per checkout attempt |
| `paymob_integration/api.py` | Whitelisted `start_checkout`. The Desk's only entry point |
| `paymob_integration/public/js/payment_request.js` | The **Pay with Paymob** button |
| `paymob_integration/hooks.py` | `doctype_js` registration |
| `paymob_integration/tests/test_amounts.py` | Conversion correctness |
| `paymob_integration/tests/test_checkout.py` | The attempt lifecycle and permissions |

---

## Task 1: Integer minor units

**Files:**
- Create: `paymob_integration/paymob/amounts.py`
- Test: `paymob_integration/tests/test_amounts.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `MINOR_UNITS: dict[str, int]`, `to_minor_units(amount, currency) -> int`,
  `from_minor_units(cents, currency) -> Decimal`, `amounts_match(expected, received) -> bool`.

- [ ] **Step 1: Write the failing test**

`paymob_integration/tests/test_amounts.py`:

```python
from decimal import Decimal

import frappe
from frappe.tests import UnitTestCase

from paymob_integration.paymob import amounts


class TestMinorUnits(UnitTestCase):
	def test_two_decimal_currency(self):
		self.assertEqual(amounts.to_minor_units("275.55", "EGP"), 27555)

	def test_the_float_that_truncates(self):
		# 0.1 + 0.2 is 0.30000000000000004 in binary floating point. Decimal is exact.
		self.assertEqual(amounts.to_minor_units(Decimal("0.1") + Decimal("0.2"), "EGP"), 30)

	def test_three_decimal_currency(self):
		self.assertEqual(amounts.to_minor_units("1.234", "OMR"), 1234)

	def test_half_a_minor_unit_rounds_up(self):
		self.assertEqual(amounts.to_minor_units("1.005", "EGP"), 101)

	def test_unsupported_currency_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			amounts.to_minor_units("10.00", "JPY")

	def test_round_trip(self):
		self.assertEqual(amounts.from_minor_units(27555, "EGP"), Decimal("275.55"))

	def test_match_is_exact(self):
		self.assertTrue(amounts.amounts_match(27555, 27555))
		self.assertFalse(amounts.amounts_match(27555, 27554))
		self.assertFalse(amounts.amounts_match(27555, 27556))
```

The last test states the rule that an overpayment is a mismatch too, not a happy surprise.

- [ ] **Step 2: Run the test and watch it fail**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_amounts`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the module**

`paymob_integration/paymob/amounts.py`:

```python
"""Money conversion. Paymob speaks integer minor units; ERPNext speaks decimals.

Every conversion in the app happens here so there is exactly one place to audit for the
missing /100 that posts a payment a hundred times too large.
"""

from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe import _

# Paymob operates in Egypt, KSA, UAE and Oman. OMR has three minor digits, not two.
MINOR_UNITS = {"EGP": 2, "SAR": 2, "AED": 2, "OMR": 3}


def to_minor_units(amount, currency):
	"""Convert an ERPNext amount to the integer Paymob expects."""
	exponent = _exponent(currency)
	quantised = Decimal(str(amount)).quantize(
		Decimal(1).scaleb(-exponent), rounding=ROUND_HALF_UP
	)
	return int(quantised.scaleb(exponent))


def from_minor_units(cents, currency):
	"""Convert a Paymob integer back to an ERPNext amount."""
	return Decimal(int(cents)).scaleb(-_exponent(currency))


def amounts_match(expected_cents, received_cents):
	"""Exact integer equality. An overpayment is a mismatch, not a bonus."""
	return int(expected_cents) == int(received_cents)


def _exponent(currency):
	if currency not in MINOR_UNITS:
		frappe.throw(_("Paymob does not support the currency {0}.").format(currency))
	return MINOR_UNITS[currency]
```

`Decimal(str(amount))` is deliberate: `Decimal(0.1)` inherits the binary error,
`Decimal("0.1")` does not.

- [ ] **Step 4: Run the test and watch it pass**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_amounts`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add paymob_integration/paymob/amounts.py paymob_integration/tests/test_amounts.py
git commit -m "feat: convert money to integer minor units with Decimal"
```

---

## Task 2: The Paymob Payment Attempt doctype

**Files:**
- Create: `paymob_integration/paymob_integration/doctype/paymob_payment_attempt/paymob_payment_attempt.json`
- Create: `paymob_integration/paymob_integration/doctype/paymob_payment_attempt/paymob_payment_attempt.py`

**Interfaces:**
- Consumes: `Payment Request`.
- Produces: the DocType every later phase reads and writes. Field names are load-bearing.

- [ ] **Step 1: Create the doctype on the site**

Module: Paymob Integration. Naming: **By fieldname** → `special_reference`. Track Changes: yes.

| Fieldname | Type | Notes |
|---|---|---|
| `special_reference` | Data | reqd, **unique**, read only. Sent to Paymob, returned as `merchant_order_id` |
| `payment_request` | Link → Payment Request | reqd, read only, In List View |
| `state` | Select | `Pending\nPaid\nFailed\nExpired\nRefunded`, default `Pending`, read only, In List View. Stored values stay English |
| `needs_human_attention` | Check | read only, In List View |
| `expected_amount_cents` | Int | reqd, read only. Frozen at creation |
| `currency` | Link → Currency | reqd, read only |
| `country` | Data | read only |
| `mode` | Select | `Test\nLive`, read only |
| `paymob_intention_id` | Data | read only |
| `paymob_order_id` | Data | read only, In List View |
| `client_secret` | **Password** | Single-session, browser-safe, but not worth exposing in list views or the API |
| `expires_at` | Datetime | read only |
| `last_polled_at` | Datetime | read only. The one field `db_set` is allowed on |
| `payment_entry` | Link → Payment Entry | read only. Set by the single write path in Phase 08 |

Permissions: **System Manager** read/write/delete; **Accounts Manager** read. No `create` for
anyone — attempts are created by code, never by hand.

- [ ] **Step 2: Add a Payment Request connection**

In the doctype's **Links** (dashboard connections) or via `Payment Request`'s form, ensure an
attempt list is reachable from the Payment Request. If Frappe's dashboard connection is
awkward for a non-standard doctype, the Phase 02 button script adds a `frm.add_custom_button`
that opens the filtered list — either is acceptable, but the merchant must be able to see the
attempts for a Payment Request without typing a filter.

- [ ] **Step 3: Export and migrate**

```bash
bench --site <site> migrate
git status --short paymob_integration/paymob_integration/doctype/paymob_payment_attempt
```

- [ ] **Step 4: Verify the unique constraint reached the database**

Run: `bench --site <site> mariadb`

```sql
SHOW INDEX FROM `tabPaymob Payment Attempt` WHERE Column_name = 'special_reference';
```

Expected: a row with `Non_unique = 0`. If it is missing, the "cannot create two live orders for
one attempt" guarantee does not exist. Fix the doctype and migrate again.

- [ ] **Step 5: Commit**

```bash
git add paymob_integration/paymob_integration/doctype/paymob_payment_attempt
git commit -m "feat: add Paymob Payment Attempt doctype"
```

---

## Task 3: Creating the intention

**Files:**
- Create: `paymob_integration/paymob/intention.py`

**Interfaces:**
- Consumes: `client.request`, `settings.base_url`, `settings.get_integration_ids`.
- Produces: `create_intention(credentials, *, amount_cents, currency, special_reference,
  billing_data, items, notification_url, redirection_url, expiration) -> dict` with keys
  `intention_id`, `order_id`, `client_secret`.

- [ ] **Step 1: Write the failing test**

Append to `paymob_integration/tests/test_checkout.py` (create the file):

```python
from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from paymob_integration.paymob import intention, settings
from paymob_integration.tests.fixtures import FAKE_SECRET_KEY, given_paymob_settings

INTENTION_RESPONSE = {
	"id": "pi_FAKE_1",
	"intention_order_id": 987654,
	"client_secret": "egy_csk_FAKE_1",
}


class TestCreateIntention(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		given_paymob_settings()
		self.credentials = settings.get_credential_set("EGP")

	def call(self, **overrides):
		payload = {
			"amount_cents": 27555,
			"currency": "EGP",
			"special_reference": "PR-00042-1",
			"billing_data": {"email": "a@b.test", "phone_number": "+201000000000"},
			"items": [],
			"notification_url": "https://site.test/api/method/webhook",
			"redirection_url": "https://site.test/paymob-result",
			"expiration": 3600,
		}
		payload.update(overrides)
		return intention.create_intention(self.credentials, **payload)

	def test_returns_the_three_identifiers(self):
		with patch(
			"paymob_integration.paymob.intention.client.request",
			return_value=INTENTION_RESPONSE,
		):
			result = self.call()

		self.assertEqual(result["intention_id"], "pi_FAKE_1")
		self.assertEqual(result["order_id"], "987654")
		self.assertEqual(result["client_secret"], "egy_csk_FAKE_1")

	def test_authenticates_with_the_secret_key(self):
		with patch(
			"paymob_integration.paymob.intention.client.request",
			return_value=INTENTION_RESPONSE,
		) as mocked:
			self.call()

		self.assertEqual(
			mocked.call_args.kwargs["headers"]["Authorization"], f"Token {FAKE_SECRET_KEY}"
		)

	def test_sends_the_amount_as_an_integer(self):
		with patch(
			"paymob_integration.paymob.intention.client.request",
			return_value=INTENTION_RESPONSE,
		) as mocked:
			self.call()

		body = mocked.call_args.kwargs["json_body"]
		self.assertIsInstance(body["amount"], int)
		self.assertEqual(body["amount"], 27555)

	def test_order_id_is_stored_as_a_string(self):
		# Paymob returns it as a number; callbacks carry it as a string. Normalise once, here.
		with patch(
			"paymob_integration.paymob.intention.client.request",
			return_value=INTENTION_RESPONSE,
		):
			result = self.call()

		self.assertIsInstance(result["order_id"], str)
```

- [ ] **Step 2: Run the test and watch it fail**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_checkout`
Expected: FAIL — `ModuleNotFoundError: ... intention`

- [ ] **Step 3: Write the module**

`paymob_integration/paymob/intention.py`:

```python
"""Creates a Paymob Intention. Called once per Paymob Payment Attempt, never retried."""

from paymob_integration.paymob import client, settings


def create_intention(
	credentials,
	*,
	amount_cents,
	currency,
	special_reference,
	billing_data,
	items,
	notification_url,
	redirection_url,
	expiration,
):
	"""Create the intention and return the three identifiers we must persist.

	Not automatically retried. A retried intention is a second live Paymob order for the same
	reference, which Paymob rejects on the unique reference — and if it did not, we would have
	two orders and one invoice.
	"""
	response = client.request(
		"POST",
		f"{settings.base_url(credentials)}/v1/intention/",
		headers={"Authorization": f"Token {credentials.get_password('secret_key')}"},
		json_body={
			"amount": int(amount_cents),
			"currency": currency,
			"payment_methods": [
				int(integration_id) for integration_id in settings.get_integration_ids(currency)
			],
			"items": items,
			"billing_data": billing_data,
			"special_reference": special_reference,
			"notification_url": notification_url,
			"redirection_url": redirection_url,
			"expiration": int(expiration),
		},
	)

	return {
		"intention_id": str(response["id"]),
		"order_id": str(response["intention_order_id"]),
		"client_secret": response["client_secret"],
	}
```

- [ ] **Step 4: Run the test and watch it pass**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_checkout`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add paymob_integration/paymob/intention.py paymob_integration/tests/test_checkout.py
git commit -m "feat: create a Paymob intention from stored credentials"
```

---

## Task 4: start_checkout

**Files:**
- Create: `paymob_integration/api.py`
- Test: `paymob_integration/tests/test_checkout.py` (append a class)

**Interfaces:**
- Consumes: `amounts.to_minor_units`, `intention.create_intention`, `settings.get_credential_set`.
- Produces: whitelisted `paymob_integration.api.start_checkout(payment_request) -> {"checkout_url", "attempt"}`,
  and `paymob_integration.api.build_checkout_url(credentials, client_secret) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `paymob_integration/tests/test_checkout.py`:

```python
import frappe

from paymob_integration import api
from paymob_integration.tests.helpers import given_submitted_payment_request


class TestStartCheckout(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		given_paymob_settings()
		self.payment_request = given_submitted_payment_request(grand_total="275.55")

	def start(self):
		with patch(
			"paymob_integration.paymob.intention.client.request",
			return_value=INTENTION_RESPONSE,
		):
			return api.start_checkout(self.payment_request.name)

	def test_returns_a_hosted_checkout_url(self):
		result = self.start()

		self.assertIn("/unifiedcheckout/", result["checkout_url"])
		self.assertIn("clientSecret=egy_csk_FAKE_1", result["checkout_url"])

	def test_only_the_public_key_reaches_the_browser(self):
		result = self.start()

		self.assertIn("publicKey=pk_test_FAKE_public", result["checkout_url"])
		self.assertNotIn(FAKE_SECRET_KEY, result["checkout_url"])

	def test_freezes_the_expected_amount_in_cents(self):
		result = self.start()

		attempt = frappe.get_doc("Paymob Payment Attempt", result["attempt"])
		self.assertEqual(attempt.expected_amount_cents, 27555)
		self.assertEqual(attempt.state, "Pending")

	def test_stores_the_identifiers_before_returning(self):
		result = self.start()

		attempt = frappe.get_doc("Paymob Payment Attempt", result["attempt"])
		self.assertEqual(attempt.paymob_intention_id, "pi_FAKE_1")
		self.assertEqual(attempt.paymob_order_id, "987654")

	def test_a_network_failure_leaves_a_pending_attempt_and_no_url(self):
		from paymob_integration.paymob.client import PaymobNetworkError

		with patch(
			"paymob_integration.paymob.intention.client.request",
			side_effect=PaymobNetworkError("down"),
		):
			with self.assertRaises(PaymobNetworkError):
				api.start_checkout(self.payment_request.name)

		attempt = frappe.get_last_doc(
			"Paymob Payment Attempt", filters={"payment_request": self.payment_request.name}
		)
		self.assertEqual(attempt.state, "Pending")
		self.assertFalse(attempt.paymob_intention_id)

	def test_a_retry_creates_a_second_attempt_with_a_new_reference(self):
		first = self.start()
		second = self.start()

		self.assertNotEqual(first["attempt"], second["attempt"])
		self.assertEqual(
			frappe.db.count(
				"Paymob Payment Attempt", {"payment_request": self.payment_request.name}
			),
			2,
		)

	def test_a_user_without_permission_is_refused(self):
		frappe.set_user("paymob-plain-user@example.test")
		try:
			with self.assertRaises(frappe.PermissionError):
				api.start_checkout(self.payment_request.name)
		finally:
			frappe.set_user("Administrator")

	def test_the_amount_is_read_from_the_database_not_the_caller(self):
		# start_checkout takes no amount argument at all. This test states that as a fact.
		import inspect

		self.assertEqual(
			list(inspect.signature(api.start_checkout).parameters), ["payment_request"]
		)
```

- [ ] **Step 2: Write the document helper the test needs**

`paymob_integration/tests/helpers.py`:

```python
"""Builds the ERPNext documents the integration tests act on."""

import frappe


def given_submitted_payment_request(grand_total="275.55", currency="EGP"):
	invoice = given_submitted_sales_invoice(grand_total=grand_total, currency=currency)
	payment_request = frappe.get_doc(
		{
			"doctype": "Payment Request",
			"payment_request_type": "Inward",
			"transaction_date": frappe.utils.nowdate(),
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice.name,
			"party_type": "Customer",
			"party": invoice.customer,
			"currency": currency,
			"grand_total": frappe.utils.flt(grand_total),
			"payment_channel": "Email",
			"email_to": "customer@example.test",
			"subject": "Payment Request",
			"message": "Please pay",
		}
	)
	payment_request.insert(ignore_permissions=True)
	payment_request.submit()
	return payment_request


def given_submitted_sales_invoice(grand_total="275.55", currency="EGP"):
	"""One line, one item, priced so the invoice total is exactly grand_total."""
	customer = _ensure_customer(currency)
	item = _ensure_item()
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": customer,
			"currency": currency,
			"conversion_rate": 1,
			"due_date": frappe.utils.nowdate(),
			"items": [{"item_code": item, "qty": 1, "rate": frappe.utils.flt(grand_total)}],
		}
	)
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	return invoice


def _ensure_customer(currency):
	name = "Paymob Test Customer"
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{"doctype": "Customer", "customer_name": name, "default_currency": currency}
		).insert(ignore_permissions=True)
	return name


def _ensure_item():
	code = "PAYMOB-TEST-ITEM"
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
	return code
```

If the test site's company currency is not EGP, add the currency and an exchange rate in this
helper rather than in each test.

- [ ] **Step 3: Run the tests and watch them fail**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_checkout`
Expected: FAIL — `ModuleNotFoundError: No module named 'paymob_integration.api'`

- [ ] **Step 4: Write the API module**

`paymob_integration/api.py`:

```python
"""Whitelisted entry points. Everything here is reachable by any logged-in user."""

import frappe
from frappe import _
from frappe.utils import add_to_date, get_url, now_datetime

from paymob_integration.paymob import amounts, intention, settings

WEBHOOK_PATH = "/api/method/paymob_integration.webhooks.processed_callback"
RESULT_PATH = "/paymob-result"


@frappe.whitelist()
def start_checkout(payment_request):
	"""Create a Paymob checkout for a submitted Payment Request and return its URL.

	Takes no amount and no currency. Both are read from the document, because everything in
	the request body is attacker-controlled.
	"""
	request = frappe.get_doc("Payment Request", payment_request)
	request.check_permission("write")

	_validate_payable(request)

	credentials = settings.get_credential_set(request.currency)
	attempt = _create_attempt(request, credentials)

	result = intention.create_intention(
		credentials,
		amount_cents=attempt.expected_amount_cents,
		currency=attempt.currency,
		special_reference=attempt.special_reference,
		billing_data=_billing_data(request),
		items=_items(request),
		notification_url=get_url(WEBHOOK_PATH),
		redirection_url=get_url(RESULT_PATH),
		expiration=settings.get_settings().intention_expiration_seconds,
	)

	attempt.db_set(
		{
			"paymob_intention_id": result["intention_id"],
			"paymob_order_id": result["order_id"],
		},
		update_modified=False,
	)
	attempt.set("client_secret", result["client_secret"])
	attempt.save(ignore_permissions=True)

	frappe.logger("paymob").info(
		f"intention created payment_request={request.name} "
		f"order_id={result['order_id']} expected_cents={attempt.expected_amount_cents}"
	)

	return {
		"attempt": attempt.name,
		"checkout_url": build_checkout_url(credentials, result["client_secret"]),
	}


def build_checkout_url(credentials, client_secret):
	"""Only the public key and the single-session client secret go into this URL."""
	return (
		f"{settings.base_url(credentials)}/unifiedcheckout/"
		f"?publicKey={credentials.public_key}&clientSecret={client_secret}"
	)


def _validate_payable(request):
	if request.docstatus != 1:
		frappe.throw(_("Submit the Payment Request before starting a payment."))
	if request.status in ("Paid", "Cancelled"):
		frappe.throw(
			_("This Payment Request is already {0}.").format(_(request.status))
		)


def _create_attempt(request, credentials):
	"""Reserve the reference first. The unique index is what stops a double checkout."""
	sequence = (
		frappe.db.count("Paymob Payment Attempt", {"payment_request": request.name}) + 1
	)
	config = settings.get_settings()
	attempt = frappe.get_doc(
		{
			"doctype": "Paymob Payment Attempt",
			"special_reference": f"{request.name}-{sequence}",
			"payment_request": request.name,
			"state": "Pending",
			"expected_amount_cents": amounts.to_minor_units(
				request.grand_total, request.currency
			),
			"currency": request.currency,
			"country": credentials.country,
			"mode": credentials.mode,
			"expires_at": add_to_date(
				now_datetime(), seconds=config.intention_expiration_seconds
			),
		}
	)
	attempt.insert(ignore_permissions=True)
	frappe.db.commit()  # the reference must survive a failure of the call that follows
	return attempt


def _billing_data(request):
	"""Paymob requires these keys. "NA" is its documented placeholder for what we lack."""
	contact = frappe.db.get_value(
		"Contact", {"name": request.contact_person}, ["first_name", "last_name"], as_dict=True
	) or {}
	return {
		"first_name": contact.get("first_name") or request.party or "NA",
		"last_name": contact.get("last_name") or "NA",
		"email": request.email_to or "NA",
		"phone_number": request.get("contact_mobile") or "NA",
		"street": "NA",
		"building": "NA",
		"floor": "NA",
		"apartment": "NA",
		"city": "NA",
		"state": "NA",
		"country": "NA",
	}


def _items(request):
	return [
		{
			"name": request.reference_name,
			"amount": amounts.to_minor_units(request.grand_total, request.currency),
			"description": request.subject or request.reference_name,
			"quantity": 1,
		}
	]
```

Two things to notice while reviewing this function. `frappe.db.commit()` after the insert is
deliberate: the reference must exist even if the Paymob call then fails, so a retry cannot reuse
it. And `db_set` here writes `paymob_intention_id`/`paymob_order_id`, which are bookkeeping
identifiers, not money or status — the documented exception in `rules/frappe-discipline.md`.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `bench --site <site> run-tests --module paymob_integration.tests.test_checkout`
Expected: PASS, 12 tests.

- [ ] **Step 6: Commit**

```bash
git add paymob_integration/api.py paymob_integration/tests
git commit -m "feat: start a Paymob checkout from a Payment Request"
```

---

## Task 5: The button

**Files:**
- Create: `paymob_integration/public/js/payment_request.js`
- Modify: `paymob_integration/hooks.py`

- [ ] **Step 1: Write the client script**

`paymob_integration/public/js/payment_request.js`:

```javascript
frappe.ui.form.on("Payment Request", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		if (["Paid", "Cancelled"].includes(frm.doc.status)) return;

		frm.add_custom_button(__("Pay with Paymob"), () => {
			frappe.call({
				method: "paymob_integration.api.start_checkout",
				args: { payment_request: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating a Paymob checkout..."),
				callback: ({ message }) => {
					if (message && message.checkout_url) {
						window.open(message.checkout_url, "_blank");
					}
				},
			});
		});

		frm.add_custom_button(__("Paymob Attempts"), () => {
			frappe.set_route("List", "Paymob Payment Attempt", {
				payment_request: frm.doc.name,
			});
		});
	},
});
```

- [ ] **Step 2: Register it in hooks.py**

Add to `paymob_integration/hooks.py`:

```python
doctype_js = {"Payment Request": "public/js/payment_request.js"}
```

- [ ] **Step 3: Build and try it by hand**

```bash
bench build --app paymob_integration
bench --site <site> clear-cache
```

Open a submitted Payment Request, click **Pay with Paymob**, and confirm a Paymob checkout page
opens with the right amount. Then open the browser's network tab, look at the response of the
`start_checkout` call, and confirm it contains **only** `attempt` and `checkout_url` — no secret
key, no API key, no HMAC secret.

- [ ] **Step 4: Add the Arabic strings**

Append to `paymob_integration/translations/ar.csv`:

```csv
Pay with Paymob,ادفع عبر باي موب
Creating a Paymob checkout...,جارٍ إنشاء صفحة الدفع...
Paymob Attempts,محاولات الدفع
Submit the Payment Request before starting a payment.,يجب اعتماد طلب الدفع قبل بدء عملية الدفع.
This Payment Request is already {0}.,طلب الدفع هذا بالفعل {0}.
Paymob does not support the currency {0}.,باي موب لا يدعم العملة {0}.
```

- [ ] **Step 5: Commit**

```bash
git add paymob_integration/public paymob_integration/hooks.py paymob_integration/translations
git commit -m "feat: add Pay with Paymob button to Payment Request"
```

---

## Task 6: Documentation

**Files:**
- Modify: `docs/reference/fields.md`, `docs/reference/states.md`, `docs/reference/decisions.md`,
  `docs/reference/endpoints.md`, `docs/user-guide/README.md`

- [ ] **Step 1: Replace the provisional field entries**

`docs/reference/fields.md` carries a note that field names are provisional. Reconcile it now:
rename the entries to the real fieldnames (`state`, `expected_amount_cents`,
`needs_human_attention`, `special_reference`, `paymob_intention_id`, `paymob_order_id`,
`client_secret`), keep both lenses, and delete the "provisional" warning. Add
`last_polled_at` with an explicit note that it is the one field `db_set` may write.

- [ ] **Step 2: Add ADR-0004**

```markdown
### ADR-0004 — Lifecycle state lives on a Paymob Payment Attempt, not on the Payment Request

**Date:** <today> · **Status:** Accepted

**Functional:** A customer whose card is declined can simply try again, and the failed try stays
visible in the history instead of being overwritten.

**Technical:**
- **Context:** `states.md` says a retry is a **new** intention, special reference, Paymob order
  and client secret, and that `failed` is terminal *for that attempt*. One set of fields on the
  Payment Request cannot hold one failed attempt and one pending attempt at the same time.
- **Decision:** A `Paymob Payment Attempt` document per checkout, named by its unique
  `special_reference`, holding state, the frozen expected amount, and the Paymob identifiers.
  The Payment Request keeps only its own ERPNext status, derived from Payment Entries.
- **Consequences / why:** the states in `states.md` are attempt states, read that way
  everywhere. Reporting on "payments" means reporting on attempts. The unique index on
  `special_reference` gives the outbound idempotency guarantee for free.
```

- [ ] **Step 3: Add the two endpoint entries**

In `docs/reference/endpoints.md` § Endpoints, document `start_checkout` (auth: `write` on the
Payment Request; side effects: creates an attempt and a Paymob intention; ledger authority: none)
and the Intention API call itself (auth: secret key; never retried; the reference is committed
before the call).

- [ ] **Step 4: Update states.md**

The five states already exist there. Add one line to `pending` making explicit that an attempt
which never reached Paymob — created, then the call failed — is also `pending`, and is resolved
by the poller in Phase 10.

- [ ] **Step 5: Write the merchant instructions**

`docs/user-guide/README.md`: how to start a payment, what the two buttons do, what to tell a
customer whose card was declined (start a new payment; the old attempt stays for the record).

- [ ] **Step 6: Commit**

```bash
git add docs
git commit -m "docs: document the payment attempt lifecycle and ADR-0004"
```

---

## Definition of Done

- [ ] Clicking **Pay with Paymob** opens a real Paymob checkout page with the correct amount.
- [ ] The attempt row exists with `paymob_intention_id` and `paymob_order_id` **before** the URL
      is returned.
- [ ] `special_reference` has a unique index in MariaDB — verified with `SHOW INDEX`.
- [ ] The expected amount is stored as an integer in minor units, converted with `Decimal`.
- [ ] `start_checkout` takes no amount, no currency, and no reference from the caller.
- [ ] A user without `write` on the Payment Request is refused.
- [ ] No secret key, API key or HMAC secret appears in the response or the checkout URL.
- [ ] A Paymob network failure raises, changes no state, and leaves a pending attempt.
- [ ] A second checkout creates a second attempt with a new reference.
- [ ] No test makes a network call.
- [ ] New strings are translated and present in `ar.csv`.
- [ ] `fields.md`, `states.md`, `endpoints.md`, `decisions.md` and the user guide updated.
- [ ] `bench --site <site> run-tests --app paymob_integration` passes.
- [ ] `pre-commit run --all-files` passes.
