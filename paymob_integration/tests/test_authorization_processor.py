"""Verified authorization/capture callbacks drive the existing processor."""

from unittest.mock import Mock, patch

import frappe

from paymob_integration.paymob import processor
from paymob_integration.tests.helpers import (
	NoCommitIntegrationTestCase,
	cleanup_fixture,
	given_attempt,
	given_transaction,
	payment_entry_count,
)


def _credentials():
	return Mock(country="Egypt", mode="Test")


def _clearing_account():
	company = frappe.defaults.get_global_default("company")
	return frappe.get_cached_value("Company", company, "default_cash_account")


class TestAuthorizationProcessor(NoCommitIntegrationTestCase):
	def setUp(self):
		credentials = patch(
			"paymob_integration.paymob.settings.get_credential_set",
			return_value=Mock(payment_account=_clearing_account()),
		)
		credentials.start()
		self.addCleanup(credentials.stop)
		self.attempt, self.request, self.invoice = given_attempt(credentials=_credentials())
		self.addCleanup(cleanup_fixture, self.attempt.name, self.request.name, self.invoice.name)

	def test_auth_holds_without_posting_and_capture_uses_the_shared_ledger_path(self):
		before = payment_entry_count()

		auth = given_transaction("Auth", "authorization-event", self.attempt.name, self.request.name)
		processor.process_transaction(auth.name)
		self.attempt.reload()
		self.assertEqual(self.attempt.state, "Authorized")
		self.assertEqual(payment_entry_count(), before)
		self.assertFalse(self.attempt.payment_entry)

		capture = given_transaction("Capture", "capture-event", self.attempt.name, self.request.name)
		processor.process_transaction(capture.name)
		self.attempt.reload()
		self.request.reload()
		self.invoice.reload()
		self.assertEqual(self.attempt.state, "Paid")
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertTrue(self.attempt.payment_entry)

		payment_entry = frappe.get_doc("Payment Entry", self.attempt.payment_entry)
		self.assertEqual(payment_entry.docstatus, 1)
		reference = payment_entry.references[0]
		self.assertEqual(reference.reference_name, self.invoice.name)
		self.assertEqual(reference.payment_request, self.request.name)
		self.assertEqual(self.invoice.outstanding_amount, 0)
		self.assertEqual(self.request.status, "Paid")
