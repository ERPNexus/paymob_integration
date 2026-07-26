"""Build the ERPNext documents checkout integration tests act on."""

import frappe


def given_submitted_payment_request(grand_total="275.55", currency="EGP"):
	"""Create a submitted invoice and its matching incoming Payment Request."""
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
			"mute_email": 1,
			"email_to": "customer@example.test",
			"subject": "Payment Request",
			"message": "Please pay",
		}
	)
	payment_request.insert(ignore_permissions=True)
	payment_request.submit()
	return payment_request, invoice


def given_submitted_sales_invoice(grand_total="275.55", currency="EGP"):
	"""Create one non-stock invoice line at exactly the requested amount."""
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
			"due_date": frappe.utils.nowdate(),
			"items": [{"item_code": item, "qty": 1, "rate": grand_total}],
		}
	)
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	return invoice


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
