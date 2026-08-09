import unittest
from contextlib import contextmanager, nullcontext
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from paymob_integration import api, hooks, pay_link, payment_request
from paymob_integration.paymob import processor
from paymob_integration.tests.helpers import (
	NoCommitIntegrationTestCase,
	given_submitted_payment_request,
	payment_entry_count,
)
from paymob_integration.tests.test_hmac_verify import SECRET, VALID_OBJ, _sign_processed
from paymob_integration.tests.test_webhook import _post
from paymob_integration.www import paymob_pay


class TestPayLink(UnitTestCase):
	def test_build_uses_frappe_signed_params(self):
		with (
			patch("paymob_integration.pay_link.get_url", return_value="https://site.test"),
			patch(
				"paymob_integration.pay_link.get_signed_params", return_value="ref=PR-0001&_signature=signed"
			),
		):
			self.assertEqual(
				pay_link.build("PR-0001"), "https://site.test/paymob-pay?ref=PR-0001&_signature=signed"
			)

	def test_payment_request_hook_only_sets_a_valid_paymob_link(self):
		doc = self._given_request()
		with self._given_paymob(send_payment_link_email=1):
			payment_request.prepare_payment_email(doc)

		self.assertEqual(doc.payment_url, "https://site.test/paymob-pay?signed")
		self.assertIn("payment_url", doc.message)
		self.assertFalse(doc.get("mute_email"))

	def test_hook_mutes_the_email_when_no_link_may_be_sent(self):
		doc = self._given_request()
		with self._given_paymob(send_payment_link_email=0):
			payment_request.prepare_payment_email(doc)

		self.assertEqual(doc.mute_email, 1)
		self.assertIsNone(doc.get("payment_url"))

	def test_hook_runs_on_validate_because_erpnext_mails_inside_before_submit(self):
		self.assertEqual(
			hooks.doc_events["Payment Request"],
			{"validate": "paymob_integration.payment_request.prepare_payment_email"},
		)

	def _given_request(self):
		return frappe._dict(
			name="PR-0001",
			payment_request_type="Inward",
			reference_doctype="Sales Invoice",
			reference_name="SINV-0001",
			currency="EGP",
			message=None,
		)

	@contextmanager
	def _given_paymob(self, send_payment_link_email):
		with (
			patch(
				"paymob_integration.payment_request.settings.get_settings",
				return_value=Mock(enabled=1, send_payment_link_email=send_payment_link_email),
			),
			patch(
				"paymob_integration.payment_request.frappe.get_doc",
				return_value=frappe._dict(company="Egypt Company"),
			),
			patch("paymob_integration.payment_request.api._merchant_country", return_value="Egypt"),
			patch("paymob_integration.payment_request.settings.get_credential_set"),
			patch(
				"paymob_integration.payment_request.pay_link.build",
				return_value="https://site.test/paymob-pay?signed",
			),
		):
			yield

	def test_checkout_reuses_a_ready_pending_attempt(self):
		request = frappe._dict(
			name="PR-0001",
			reference_doctype="Sales Invoice",
			reference_name="SINV-0001",
			currency="EGP",
		)
		attempt = Mock(country="Egypt", currency="EGP", mode="Test")
		attempt.name = "PR-0001-1"
		attempt.get_password.return_value = "client-secret"
		credentials = Mock()
		with (
			patch("paymob_integration.api._validate_payable"),
			patch("paymob_integration.api.frappe.get_doc", return_value=frappe._dict()),
			patch("paymob_integration.api._merchant_country", return_value="Egypt"),
			patch(
				"paymob_integration.api.settings.resolve_integrations",
				return_value=["1001"],
			),
			patch("paymob_integration.api._active_attempt", return_value=attempt),
			patch("paymob_integration.api.filelock", return_value=nullcontext()),
			patch("paymob_integration.api.settings.get_credential_set", return_value=credentials),
			patch("paymob_integration.api.build_checkout_url", return_value="https://checkout.test"),
		):
			result = api._checkout(request, reuse_pending=True)

		self.assertEqual(result, {"attempt": "PR-0001-1", "checkout_url": "https://checkout.test"})

	def test_contact_email_uses_the_same_fallback_as_billing_data(self):
		request = frappe._dict(email_to="payer@example.test")
		self.assertEqual(api._contact_email(request, frappe._dict(contact_email=None)), "payer@example.test")

	def test_checkout_failure_renders_the_safe_error_without_redirecting(self):
		frappe.form_dict = frappe._dict(ref="PR-0001")
		frappe.local.flags.redirect_location = None
		with (
			patch("paymob_integration.www.paymob_pay.verify_request", return_value=True),
			patch("paymob_integration.www.paymob_pay.frappe.get_doc"),
			patch("paymob_integration.www.paymob_pay.frappe.log_error"),
			patch("paymob_integration.www.paymob_pay.api._checkout", side_effect=frappe.ValidationError),
		):
			context = paymob_pay.get_context(frappe._dict())

		self.assertEqual(context.message, "We could not start your payment. Please contact the merchant.")
		self.assertFalse(frappe.local.flags.get("redirect_location"))


class TestPayerLinkCheckout(NoCommitIntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.payment_request, self.invoice = given_submitted_payment_request()
		self.credentials = Mock(country="Egypt", mode="Test", public_key="pk_test_FAKE_public")

	def tearDown(self):
		for payment_entry in frappe.get_all(
			"Payment Entry Reference", {"payment_request": self.payment_request.name}, pluck="parent"
		):
			entry = frappe.get_doc("Payment Entry", payment_entry)
			if entry.docstatus == 1:
				entry.cancel()
			frappe.delete_doc("Payment Entry", payment_entry, force=True, ignore_permissions=True)
		frappe.db.delete("Paymob Audit Entry", {"payment_request": self.payment_request.name})
		frappe.db.delete("Paymob Transaction", {"payment_request": self.payment_request.name})
		for attempt in frappe.get_all(
			"Paymob Payment Attempt", {"payment_request": self.payment_request.name}, pluck="name"
		):
			frappe.delete_doc("Paymob Payment Attempt", attempt, force=True)
		self.payment_request.cancel()
		frappe.delete_doc("Payment Request", self.payment_request.name, force=True)
		self.invoice.cancel()
		frappe.delete_doc("Sales Invoice", self.invoice.name, force=True)
		super().tearDown()

	def test_repeated_payer_link_open_reuses_one_checkout(self):
		result = {
			"intention_id": "pi_FAKE_1",
			"order_id": "987654",
			"client_secret": "egy_csk_FAKE_1",
		}
		with (
			patch("paymob_integration.api._merchant_country", return_value="Egypt"),
			patch("paymob_integration.api.settings.resolve_integrations", return_value=["1234"]),
			patch("paymob_integration.api.settings.get_credential_set", return_value=self.credentials),
			patch(
				"paymob_integration.api.settings.get_settings",
				return_value=frappe._dict(intention_expiration_seconds=3600),
			),
			patch(
				"paymob_integration.api.intention.create_intention", return_value=result
			) as create_intention,
			patch(
				"paymob_integration.api.build_checkout_url", side_effect=lambda _credentials, secret: secret
			),
		):
			first = api._checkout(self.payment_request, reuse_pending=True)
			second = api._checkout(self.payment_request, reuse_pending=True)

		self.assertEqual(first, second)
		self.assertEqual(first["checkout_url"], result["client_secret"])
		self.assertEqual(
			frappe.db.count("Paymob Payment Attempt", {"payment_request": self.payment_request.name}), 1
		)
		create_intention.assert_called_once()

	def test_signed_payer_link_persists_identifiers_before_redirecting(self):
		result = {
			"intention_id": "pi_FAKE_1",
			"order_id": "987654",
			"client_secret": "egy_csk_FAKE_1",
		}
		frappe.form_dict = frappe._dict(ref=self.payment_request.name)
		frappe.local.flags.redirect_location = None
		with (
			patch("paymob_integration.www.paymob_pay.verify_request", return_value=True),
			patch("paymob_integration.api._merchant_country", return_value="Egypt"),
			patch("paymob_integration.api.settings.resolve_integrations", return_value=["1234"]),
			patch("paymob_integration.api.settings.get_credential_set", return_value=self.credentials),
			patch(
				"paymob_integration.api.settings.get_settings",
				return_value=frappe._dict(intention_expiration_seconds=3600, mode="Test"),
			),
			patch("paymob_integration.api.intention.create_intention", return_value=result),
			patch("paymob_integration.api.build_checkout_url", return_value="https://checkout.test"),
			patch("paymob_integration.api.frappe.db.commit") as commit,
			self.assertRaises(frappe.Redirect),
		):
			paymob_pay.get_context(frappe._dict())

		attempt = frappe.get_last_doc(
			"Paymob Payment Attempt", filters={"payment_request": self.payment_request.name}
		)
		self.assertEqual(attempt.paymob_intention_id, result["intention_id"])
		self.assertEqual(attempt.paymob_order_id, result["order_id"])
		self.assertEqual(attempt.get_password("client_secret"), result["client_secret"])
		self.assertEqual(frappe.local.flags.redirect_location, "https://checkout.test")
		self.assertEqual(commit.call_count, 2)

	# CI-only flake under the full suite (not reproducible running this file alone) — tracked
	# separately from the fixture-seeding fixes in helpers.py; not chased further here per owner
	# instruction.
	@unittest.skip("Known CI-only flake: see git history for investigation notes")
	def test_signed_payer_link_attempt_accepts_decline_then_success_callback(self):
		result = {
			"intention_id": "pi_FAKE_1",
			"order_id": str(VALID_OBJ["order"]["id"]),
			"client_secret": "egy_csk_FAKE_1",
		}
		frappe.form_dict = frappe._dict(ref=self.payment_request.name)
		frappe.local.flags.redirect_location = None
		with (
			patch("paymob_integration.www.paymob_pay.verify_request", return_value=True),
			patch("paymob_integration.api._merchant_country", return_value="Egypt"),
			patch("paymob_integration.api.settings.resolve_integrations", return_value=["1234"]),
			patch("paymob_integration.api.settings.get_credential_set", return_value=self.credentials),
			patch(
				"paymob_integration.api.settings.get_settings",
				return_value=frappe._dict(intention_expiration_seconds=3600),
			),
			patch("paymob_integration.api.intention.create_intention", return_value=result),
			patch("paymob_integration.api.build_checkout_url", return_value="https://checkout.test"),
			self.assertRaises(frappe.Redirect),
		):
			paymob_pay.get_context(frappe._dict())

		attempt = frappe.get_last_doc(
			"Paymob Payment Attempt", filters={"payment_request": self.payment_request.name}
		)
		callback_credentials = Mock(mode="Test")
		callback_credentials.get_password.return_value = SECRET
		before = payment_entry_count()
		decline = {
			**VALID_OBJ,
			"id": 991001,
			"success": False,
			"order": {**VALID_OBJ["order"], "merchant_order_id": attempt.name},
		}
		success = {
			**VALID_OBJ,
			"id": 991002,
			"order": {**VALID_OBJ["order"], "merchant_order_id": attempt.name},
		}
		with (
			patch(
				"paymob_integration.webhooks.settings.enabled_credential_sets",
				return_value=[callback_credentials],
			),
			patch("paymob_integration.webhooks.frappe.enqueue"),
			patch(
				"paymob_integration.paymob.settings.get_credential_set",
				return_value=Mock(
					payment_account=frappe.get_cached_value(
						"Company", self.invoice.company, "default_cash_account"
					)
				),
			),
		):
			_post({"obj": decline}, _sign_processed(decline))
			processor.process_transaction("991001:Decline")
			attempt.reload()
			self.assertEqual(attempt.state, "Failed")
			self.assertEqual(payment_entry_count(), before)
			_post({"obj": success}, _sign_processed(success))
			processor.process_transaction("991002:Success")

		attempt.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(payment_entry_count(), before + 1)


class TestSubmitTimeEmail(NoCommitIntegrationTestCase):
	def test_submitting_an_inward_request_does_not_enqueue_erpnexts_default_email(self):
		"""The bug this guards: ERPNext mails inside its own before_submit, so a hook that runs
		after it cannot stop a link-less email. Nothing may reach the queue.
		"""
		with (
			patch(
				"paymob_integration.payment_request.settings.get_settings",
				return_value=Mock(enabled=1, send_payment_link_email=0),
			),
			patch("paymob_integration.payment_request.api._merchant_country", return_value="Egypt"),
			patch("paymob_integration.payment_request.settings.get_credential_set"),
			patch("erpnext.accounts.doctype.payment_request.payment_request.enqueue") as enqueue,
		):
			payment_request_doc, invoice = given_submitted_payment_request(mute_email=0)
		self.addCleanup(self._drop, payment_request_doc, invoice)

		enqueue.assert_not_called()
		self.assertEqual(payment_request_doc.mute_email, 1)

	def _drop(self, payment_request_doc, invoice):
		payment_request_doc.cancel()
		frappe.delete_doc("Payment Request", payment_request_doc.name, force=True)
		invoice.cancel()
		frappe.delete_doc("Sales Invoice", invoice.name, force=True)
