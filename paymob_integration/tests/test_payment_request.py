from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from paymob_integration import payment_request

CREDENTIALS = Mock()


class TestCustomerEmail(UnitTestCase):
	def test_prefers_the_reference_documents_contact_email(self):
		doc = frappe._dict(party_type="Customer", party="CUST-00001")
		source = frappe._dict(contact_email="payer@example.test")

		self.assertEqual(payment_request._customer_email(doc, source), "payer@example.test")

	def test_falls_back_to_the_customers_own_email(self):
		doc = frappe._dict(party_type="Customer", party="CUST-00001")
		source = frappe._dict(contact_email=None)

		with patch(
			"paymob_integration.payment_request.frappe.db.get_value", return_value="customer@example.test"
		):
			self.assertEqual(payment_request._customer_email(doc, source), "customer@example.test")

	def test_falls_back_to_any_linked_contact_when_none_is_primary(self):
		"""Customer.email_id is blank whenever no linked Contact is flagged is_primary_contact,
		even if a usable email exists on a non-primary Contact — this is that case."""
		doc = frappe._dict(party_type="Customer", party="CUST-00001")
		source = frappe._dict(contact_email=None)

		with (
			patch("paymob_integration.payment_request.frappe.db.get_value") as get_value,
			patch("paymob_integration.payment_request.get_default_contact", return_value="-Mohamed Ahmed"),
		):
			get_value.side_effect = ["", "customer@example.test"]
			self.assertEqual(payment_request._customer_email(doc, source), "customer@example.test")

	def test_returns_none_when_no_customer_email_exists(self):
		doc = frappe._dict(party_type="Customer", party="CUST-00001")
		source = frappe._dict(contact_email=None)

		with (
			patch("paymob_integration.payment_request.frappe.db.get_value", return_value=None),
			patch("paymob_integration.payment_request.get_default_contact", return_value=None),
		):
			self.assertIsNone(payment_request._customer_email(doc, source))

	def test_never_falls_back_to_a_non_customer_party(self):
		doc = frappe._dict(party_type="Supplier", party="SUP-00001")
		source = frappe._dict(contact_email=None)

		self.assertIsNone(payment_request._customer_email(doc, source))


class TestPreparePaymentEmail(UnitTestCase):
	def call(self, doc, source, send_payment_link_email=1):
		with (
			patch(
				"paymob_integration.payment_request.settings.get_settings",
				return_value=frappe._dict(enabled=1, send_payment_link_email=send_payment_link_email),
			),
			patch("paymob_integration.payment_request.settings.is_enabled", return_value=True),
			patch("paymob_integration.payment_request.settings.get_credential_set", return_value=CREDENTIALS),
			patch("paymob_integration.payment_request.api._merchant_country", return_value="Egypt"),
			patch("paymob_integration.payment_request.frappe.get_doc", return_value=source),
			patch("paymob_integration.payment_request.pay_link.build", return_value="https://pay.test/x"),
		):
			payment_request.prepare_payment_email(doc)

	def test_mutes_email_when_no_customer_email_is_found(self):
		doc = frappe._dict(
			payment_request_type="Inward",
			reference_doctype="Sales Invoice",
			reference_name="ACC-SINV-00001",
			party_type="Customer",
			party="CUST-00001",
			currency="EGP",
			email_to="Administrator",
			message=None,
			mute_email=0,
		)
		source = frappe._dict(contact_email=None)

		with patch("paymob_integration.payment_request.frappe.db.get_value", return_value=None):
			self.call(doc, source)

		self.assertEqual(doc.mute_email, 1)
		self.assertEqual(doc.email_to, "Administrator")

	def test_overwrites_email_to_with_the_customers_email(self):
		doc = frappe._dict(
			payment_request_type="Inward",
			reference_doctype="Sales Invoice",
			reference_name="ACC-SINV-00001",
			party_type="Customer",
			party="CUST-00001",
			currency="EGP",
			email_to="Administrator",
			message=None,
			mute_email=0,
		)
		source = frappe._dict(contact_email="payer@example.test")

		self.call(doc, source)

		self.assertEqual(doc.email_to, "payer@example.test")
		self.assertEqual(doc.payment_url, "https://pay.test/x")
		self.assertNotEqual(doc.mute_email, 1)
