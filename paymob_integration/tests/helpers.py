"""Build the ERPNext documents checkout integration tests act on."""

from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from paymob_integration import api


class NoCommitIntegrationTestCase(FrappeTestCase):
	"""Keep each integration-test class inside Frappe's rollback transaction."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# ERPNext only seeds this via the setup wizard; a fresh `bench new-site` + `install-app`
		# never runs it, so Company.create_default_warehouses() fails looking up "Transit".
		if not frappe.db.exists("Warehouse Type", "Transit"):
			frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert()
		# A name paymob owns exclusively: "_Test Company" is ERPNext core's own fixture name, and
		# reusing it collides with whatever currency an earlier, unrelated test run left it in.
		company = "_Test Paymob Company"
		if not frappe.db.exists("Company", company):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": company,
					"country": "India",
					"default_currency": "EGP",
					"create_chart_of_accounts_based_on": "Standard Template",
					"chart_of_accounts": "Standard",
				}
			).save()
		frappe.defaults.set_global_default("company", company)
		# Same gap as Warehouse Type above: the setup wizard seeds the running Fiscal Year, a
		# fresh site has none, and every submitted document validates its posting date against one.
		# Checked by date coverage AND company scope: a Fiscal Year restricted to other companies
		# (a "Fiscal Year Company" child row) covers the date but not `company`, and ERPNext's own
		# `get_fiscal_year` would still reject it — see `erpnext.accounts.utils._get_fiscal_years`.
		today = frappe.utils.nowdate()
		unrestricted_or_scoped = frappe.db.sql(
			"""
			select fy.name from `tabFiscal Year` fy
			where fy.disabled = 0 and fy.year_start_date <= %(today)s and fy.year_end_date >= %(today)s
			and (
				not exists (select 1 from `tabFiscal Year Company` fyc where fyc.parent = fy.name)
				or exists (
					select 1 from `tabFiscal Year Company` fyc
					where fyc.parent = fy.name and fyc.company = %(company)s
				)
			)
			""",
			{"today": today, "company": company},
		)
		if not unrestricted_or_scoped:
			# Scoped to `company` (not left global): an unscoped Fiscal Year here would overlap
			# ERPNext's own unrestricted "2025-2026"/"2026-2027" test fixtures and fail
			# `validate_overlap`, which only allows overlapping ranges when they're company-scoped.
			frappe.get_doc(
				{
					"doctype": "Fiscal Year",
					"year": "Paymob Test Fiscal Year",
					"year_start_date": f"{today[:4]}-01-01",
					"year_end_date": f"{today[:4]}-12-31",
					"companies": [{"company": company}],
				}
			).insert()
			# ERPNext's `get_fiscal_year` reads a Redis hash keyed by company (`_get_fiscal_years`);
			# an earlier lookup for this brand-new company (e.g. from the Company save above) can
			# have cached an empty result before this Fiscal Year existed. `on_update` clears the
			# whole hash, but only for saves that go through it — force it here too, cheaply.
			frappe.cache().delete_key("fiscal_years")
		commit = patch.object(frappe.db, "commit", return_value=None)
		commit.start()
		cls.addClassCleanup(commit.stop)


def mock_credentials():
	row = Mock()
	row.country = "Egypt"
	row.mode = "Test"
	return row


def given_attempt(state="Pending", credentials=None):
	"""A Paymob Payment Attempt against a fresh submitted Payment Request. Caller registers
	`cleanup_fixture` via `addCleanup` — this function does not know about the test case.
	"""
	payment_request, invoice = given_submitted_payment_request()
	attempt = api._create_attempt(payment_request, credentials or mock_credentials())
	if state != "Pending":
		attempt.state = state
		attempt.save(ignore_permissions=True)
	return attempt, payment_request, invoice


def cleanup_fixture(attempt_name, payment_request_name, invoice_name):
	"""Cancel/delete the Payment Entry first — it blocks deleting both the Payment Request and
	the Sales Invoice while submitted.

	A refund Payment Entry is never added to `Payment Entry Reference` (fields.md — ERPNext would
	reject the allocation against an already-zero outstanding balance); it only carries the custom
	`payment_request` link field, so both sources are queried here or refund entries leak past
	cleanup and block later Payment Request/Sales Invoice deletion with a dangling audit-entry link.
	"""
	# Audit entries (which link to a refund Payment Entry via `payment_entry`) must go first — a
	# submitted Payment Entry can't be cancelled while a Paymob Audit Entry still links to it.
	frappe.db.delete("Paymob Audit Entry", {"payment_request": payment_request_name})
	original_charge = frappe.get_all(
		"Payment Entry Reference", {"payment_request": payment_request_name}, pluck="parent"
	)
	refunds = frappe.get_all("Payment Entry", {"payment_request": payment_request_name}, pluck="name")
	for payment_entry in set(original_charge) | set(refunds):
		pe = frappe.get_doc("Payment Entry", payment_entry)
		if pe.docstatus == 1:
			pe.cancel()
		frappe.delete_doc("Payment Entry", payment_entry, force=True, ignore_permissions=True)
	frappe.db.delete("Paymob Transaction", {"payment_request": payment_request_name})
	frappe.delete_doc("Paymob Payment Attempt", attempt_name, force=True, ignore_permissions=True)
	payment_request = frappe.get_doc("Payment Request", payment_request_name)
	if payment_request.docstatus == 1:
		payment_request.cancel()
	frappe.delete_doc("Payment Request", payment_request_name, force=True, ignore_permissions=True)
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	if invoice.docstatus == 1:
		invoice.cancel()
	frappe.delete_doc("Sales Invoice", invoice_name, force=True, ignore_permissions=True)


def given_transaction(
	event_kind,
	txn_id,
	attempt=None,
	payment_request=None,
	amount_cents=27555,
	currency="EGP",
	**overrides,
):
	doc = frappe.get_doc(
		{
			"doctype": "Paymob Transaction",
			"paymob_transaction_id": txn_id,
			"event_kind": event_kind,
			"attempt": attempt,
			"payment_request": payment_request,
			"amount_cents": amount_cents,
			"currency": currency,
			"success": event_kind == "Success",
			"pending": event_kind == "Pending",
			"is_refunded": event_kind == "Refund",
			"is_voided": False,
			"source": "Webhook",
			"hmac_verified": 1,
			"received_at": frappe.utils.now_datetime(),
			"raw_payload": "{}",
			**overrides,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def payment_entry_count():
	return frappe.db.count("Payment Entry")


def given_user_with_role(role):
	"""A fresh user holding exactly one role, for permission-gate tests."""
	email = f"paymob-{frappe.scrub(role)}@example.test"
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
	return email


def given_submitted_payment_request(grand_total="275.55", currency="EGP", mute_email=1):
	"""Create a submitted invoice and its matching incoming Payment Request.

	`mute_email` defaults to 1 so the usual fixture never touches the mail queue; pass 0 to let a
	test observe what ERPNext's own submit-time email would do.
	"""
	invoice = given_submitted_sales_invoice(grand_total, currency)
	payment_request = frappe.get_doc(
		{
			"doctype": "Payment Request",
			"payment_request_type": "Inward",
			"transaction_date": frappe.utils.nowdate(),
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice.name,
			"party_type": "Customer",
			"party": invoice.customer,
			"company": invoice.company,
			"currency": currency,
			"grand_total": grand_total,
			"payment_channel": "Email",
			"mute_email": mute_email,
			"email_to": "customer@example.test",
			"subject": "Payment Request",
			"message": "Please pay",
		}
	)
	payment_request.insert(ignore_permissions=True)
	payment_request.submit()
	return payment_request, invoice


def given_submitted_sales_invoice(grand_total="275.55", currency="EGP"):
	"""Create one non-stock invoice line at exactly the requested amount.

	`disable_rounded_total` avoids a mismatch on sites whose Currency master rounds to a whole
	unit (`smallest_currency_fraction_value = 0`) — without it, `outstanding_amount` silently
	differs from `grand_total`, which any test asserting the ledger down to the cent depends on.
	"""
	company = frappe.defaults.get_global_default("company")
	customer = _ensure_customer(currency)
	item = _ensure_item()
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": customer,
			"currency": currency,
			"conversion_rate": 1,
			"selling_price_list": _ensure_price_list(currency),
			"disable_rounded_total": 1,
			"due_date": frappe.utils.nowdate(),
			"items": [{"item_code": item, "qty": 1, "rate": grand_total}],
		}
	)
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	return invoice


def _ensure_price_list(currency):
	# Same setup-wizard gap as the fixtures in NoCommitIntegrationTestCase.setUpClass: a fresh
	# site has no "Standard Selling" Price List, and every Sales Invoice needs one.
	name = f"Paymob Test Selling {currency}"
	if not frappe.db.exists("Price List", name):
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": name,
				"enabled": 1,
				"buying": 0,
				"selling": 1,
				"currency": currency,
			}
		).insert(ignore_permissions=True)
	return name


def _ensure_customer(currency):
	name = "Paymob Test Customer"
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
				"default_currency": currency,
			}
		).insert(ignore_permissions=True)
	return name


def _ensure_item():
	# Sites that scope Items per Company (e.g. Modar) require the code to start with "<abbr>-".
	abbr = frappe.db.get_value("Company", frappe.defaults.get_global_default("company"), "abbr")
	code = f"{abbr}-PAYMOB-TEST-ITEM" if abbr else "PAYMOB-TEST-ITEM"
	if not frappe.db.exists("UOM", "Nos"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Nos", "must_be_whole_number": 1}).insert(
			ignore_permissions=True
		)
	item_group = "Paymob Test Items"
	if not frappe.db.exists("Item Group", item_group):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": item_group, "is_group": 0}).insert(
			ignore_permissions=True
		)
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": item_group,
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
	return code
