"""Verified authorization/capture callbacks drive the existing processor."""

from unittest.mock import Mock, patch

import frappe

from paymob_integration import api
from paymob_integration.paymob import processor
from paymob_integration.tests.helpers import (
	NoCommitIntegrationTestCase,
	cleanup_fixture,
	given_attempt,
	given_submitted_payment_request,
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


class TestUnrequestedCapture(NoCommitIntegrationTestCase):
	"""A hold Paymob captured on its own — the Integration ID is not auth-only in Paymob's
	dashboard, so the merchant's authorize-only promise was silently broken.
	"""

	def setUp(self):
		credentials = patch(
			"paymob_integration.paymob.settings.get_credential_set",
			return_value=Mock(payment_account=_clearing_account()),
		)
		credentials.start()
		self.addCleanup(credentials.stop)
		self.attempt, self.request, self.invoice = given_attempt(
			credentials=_credentials(), authorize_only=True
		)
		self.addCleanup(cleanup_fixture, self.attempt.name, self.request.name, self.invoice.name)

	def _process(self, event_kind):
		txn = given_transaction(
			event_kind, f"{event_kind}-{self.attempt.name}", self.attempt.name, self.request.name
		)
		processor.process_transaction(txn.name)
		self.attempt.reload()

	def _flags(self):
		return frappe.get_all(
			"Paymob Audit Entry",
			filters={"attempt": self.attempt.name, "event": "Capture Not Requested"},
			fields=["name", "needs_action"],
		)

	def test_a_capture_nobody_requested_still_posts_and_is_flagged(self):
		before = payment_entry_count()

		self._process("Auth")
		self.assertEqual(self.attempt.state, "Authorized")
		self._process("Capture")

		self.assertEqual(self.attempt.state, "Paid")
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(self.attempt.needs_human_attention, 1)
		flags = self._flags()
		self.assertEqual(len(flags), 1)
		self.assertEqual(flags[0].needs_action, 1)

	def test_a_capture_the_merchant_requested_is_not_flagged(self):
		self._process("Auth")
		self.attempt.db_set("capture_requested_at", frappe.utils.now_datetime())

		self._process("Capture")

		self.assertEqual(self.attempt.state, "Paid")
		self.assertEqual(self.attempt.needs_human_attention, 0)
		self.assertEqual(self._flags(), [])


class TestConfiguredCaptureModeDrivesTheOutcome(NoCommitIntegrationTestCase):
	"""Checkout resolves capture mode from Paymob Settings, not a per-request field — the path
	`given_attempt`-based tests above skip by setting `authorize_only` on the fixture directly.
	"""

	def setUp(self):
		credentials = patch(
			"paymob_integration.paymob.settings.get_credential_set",
			return_value=Mock(country="Egypt", mode="Test", payment_account=_clearing_account()),
		)
		credentials.start()
		self.addCleanup(credentials.stop)
		self.payment_request, self.invoice = given_submitted_payment_request()

	def _checkout(self, capture_mode, integration_ids):
		with (
			patch(
				"paymob_integration.paymob.settings.resolve_integrations",
				return_value=(capture_mode, integration_ids),
			),
			patch(
				"paymob_integration.paymob.settings.get_settings",
				return_value=frappe._dict(intention_expiration_seconds=3600),
			),
			patch(
				"paymob_integration.api.intention.create_intention",
				return_value={
					"intention_id": "pi_FAKE_1",
					"order_id": "987654",
					"client_secret": "egy_csk_FAKE_1",
				},
			),
		):
			result = api.start_checkout(self.payment_request.name)
		attempt = frappe.get_doc("Paymob Payment Attempt", result["attempt"])
		self.addCleanup(cleanup_fixture, attempt.name, self.payment_request.name, self.invoice.name)
		return attempt

	def test_configured_authorize_only_holds_without_posting(self):
		attempt = self._checkout("Authorize Only", ["1002"])
		before = payment_entry_count()

		auth = given_transaction("Auth", "cm-auth-hold", attempt.name, self.payment_request.name)
		processor.process_transaction(auth.name)
		attempt.reload()

		self.assertEqual(attempt.state, "Authorized")
		self.assertEqual(payment_entry_count(), before)
		self.assertFalse(attempt.payment_entry)
		self.assertNotEqual(frappe.get_doc("Payment Request", self.payment_request.name).status, "Paid")
		self.invoice.reload()
		self.assertNotEqual(self.invoice.outstanding_amount, 0)
		self.assertEqual(attempt.needs_human_attention, 0)

	def test_a_verified_capture_then_pays_and_posts(self):
		attempt = self._checkout("Authorize Only", ["1002"])
		before = payment_entry_count()
		auth = given_transaction("Auth", "cm-auth-then-capture", attempt.name, self.payment_request.name)
		processor.process_transaction(auth.name)
		attempt.reload()
		attempt.db_set("capture_requested_at", frappe.utils.now_datetime())

		capture = given_transaction(
			"Capture", "cm-capture-after-auth", attempt.name, self.payment_request.name
		)
		processor.process_transaction(capture.name)
		attempt.reload()

		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(payment_entry_count(), before + 1)
		payment_entry = frappe.get_doc("Payment Entry", attempt.payment_entry)
		self.assertEqual(payment_entry.docstatus, 1)
		reference = payment_entry.references[0]
		self.assertEqual(reference.reference_name, self.invoice.name)
		self.invoice.reload()
		self.assertEqual(self.invoice.outstanding_amount, 0)
		self.assertEqual(frappe.get_doc("Payment Request", self.payment_request.name).status, "Paid")
		self.assertFalse(attempt.capture_requested_at)

	def test_configured_auto_capture_pays_directly(self):
		attempt = self._checkout("Auto Capture", ["1001"])
		before = payment_entry_count()

		success = given_transaction("Success", "cm-success-direct", attempt.name, self.payment_request.name)
		processor.process_transaction(success.name)
		attempt.reload()

		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertFalse(attempt.authorize_only)
		self.assertEqual(
			frappe.get_all(
				"Paymob Audit Entry",
				filters={"attempt": attempt.name, "event": "Capture Not Requested"},
			),
			[],
		)
