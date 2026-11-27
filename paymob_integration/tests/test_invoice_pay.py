from unittest.mock import patch

import frappe

from paymob_integration import invoice_pay
from paymob_integration.tests.helpers import NoCommitIntegrationTestCase, given_submitted_sales_invoice


class TestInvoicePay(NoCommitIntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.enabled = patch("paymob_integration.invoice_pay.enabled_for", return_value=True)
		self.enabled.start()
		self.invoice = given_submitted_sales_invoice("120.00")

	def tearDown(self):
		self.enabled.stop()
		super().tearDown()

	def test_link_asks_for_the_whole_outstanding_and_is_reused(self):
		first = invoice_pay.link_for(self.invoice.name)
		second = invoice_pay.link_for(self.invoice.name)

		self.assertEqual(first["amount"], 120.0)
		self.assertEqual(first["state"], "Open")
		self.assertIn("/paymob-pay?", first["url"])
		self.assertEqual(first["payment_request"], second["payment_request"])

	def test_a_lower_outstanding_replaces_the_old_request(self):
		old = invoice_pay.link_for(self.invoice.name)
		frappe.db.set_value("Sales Invoice", self.invoice.name, "outstanding_amount", 70)

		new = invoice_pay.link_for(self.invoice.name)

		self.assertNotEqual(old["payment_request"], new["payment_request"])
		self.assertEqual(new["amount"], 70.0)
		self.assertEqual(frappe.db.get_value("Payment Request", old["payment_request"], "docstatus"), 2)

	def test_nothing_owed_means_no_link(self):
		frappe.db.set_value("Sales Invoice", self.invoice.name, "outstanding_amount", 0)
		self.assertRaises(frappe.ValidationError, invoice_pay.link_for, self.invoice.name)
