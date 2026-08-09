"""Verified reversal callbacks create on-account Payment Entries exactly once."""

from unittest.mock import Mock, patch

import frappe

from paymob_integration.paymob import client, processor, transactions
from paymob_integration.tests.helpers import (
	NoCommitIntegrationTestCase,
	cleanup_fixture,
	given_attempt,
	given_transaction,
	payment_entry_count,
)


def _credentials():
	return Mock(country="Egypt", mode="Test")


def _child_obj(txn_id, charged, amount_cents, refunded_amount_cents, currency="EGP", **overrides):
	"""The real shape Transaction Inquiry returns for a signed child refund transaction
	(ADR-0034): `has_parent_transaction`, `is_refund`, and `success` are all set, and
	`parent_transaction` names the charge it reverses.
	"""
	return {
		"id": txn_id,
		"amount_cents": amount_cents,
		"currency": currency,
		"success": True,
		"pending": False,
		"is_refunded": False,
		"is_voided": False,
		"has_parent_transaction": True,
		"is_refund": True,
		"parent_transaction": charged.paymob_transaction_id,
		"refunded_amount_cents": refunded_amount_cents,
		**overrides,
	}


def _clearing_account():
	company = frappe.defaults.get_global_default("company")
	return frappe.get_cached_value("Company", company, "default_cash_account")


class TestRefundLedger(NoCommitIntegrationTestCase):
	def setUp(self):
		credentials = patch(
			"paymob_integration.paymob.settings.get_credential_set",
			return_value=Mock(payment_account=_clearing_account()),
		)
		credentials.start()
		self.addCleanup(credentials.stop)

	def _paid_attempt(self):
		attempt, request, invoice = given_attempt(credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		# Frappe's IntegrationTestCase only rolls back at class teardown (no per-test savepoint —
		# see frappe.tests.classes.integration_test_case), so every call in this class shares one
		# transaction: the id must be unique per call, not a literal reused across test methods.
		success = given_transaction("Success", f"success-{attempt.name}", attempt.name, request.name)
		processor.process_transaction(success.name)
		return attempt, request

	def test_child_refund_posts_its_signed_delta(self):
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		attempt.db_set("refund_requested_at", frappe.utils.now_datetime())
		refund = given_transaction(
			"Refund",
			"refund-child",
			attempt.name,
			request.name,
			amount_cents=10000,
			has_parent_transaction=1,
			refunded_amount_cents=27555,
		)

		processor.process_transaction(refund.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(attempt.state, "Partially Refunded")
		self.assertEqual(attempt.refunded_amount_cents, 10000)
		self.assertIsNone(attempt.refund_requested_at)
		entry = frappe.get_doc(
			"Payment Entry", frappe.get_all("Payment Entry", order_by="creation desc", pluck="name")[0]
		)
		self.assertEqual(entry.payment_type, "Pay")
		self.assertEqual(entry.docstatus, 1)
		self.assertFalse(entry.references)
		self.assertEqual(entry.payment_request, request.name)
		refund.reload()
		self.assertEqual(refund.payment_entry, entry.name)

	def test_the_unsigned_cumulative_field_never_drives_the_amount(self):
		"""`refunded_amount_cents` on the callback is not HMAC-signed (ADR-0017); only the
		child transaction's own signed `amount_cents` may reach the ledger.
		"""
		attempt, request = self._paid_attempt()
		refund = given_transaction(
			"Refund",
			"refund-unsigned-check",
			attempt.name,
			request.name,
			amount_cents=10000,
			has_parent_transaction=1,
			refunded_amount_cents=27555,  # lying: claims the full charge was refunded
		)

		processor.process_transaction(refund.name)

		entry = frappe.get_doc(
			"Payment Entry", frappe.get_all("Payment Entry", order_by="creation desc", pluck="name")[0]
		)
		self.assertEqual(entry.paid_amount, 100)

	def test_routine_parent_resend_with_matching_total_is_quiet(self):
		"""The parent re-send arrives on every refund, signed or not. When Paymob's cumulative
		total already matches what this app posted, it is routine bookkeeping — no inquiry call,
		no audit entry, no flag, just marked processed.
		"""
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		attempt.db_set("refund_requested_at", frappe.utils.now_datetime())
		lock = attempt.refund_requested_at
		parent = given_transaction(
			"Refund",
			"refund-parent-routine",
			attempt.name,
			request.name,
			amount_cents=10000,
			has_parent_transaction=0,
			refunded_amount_cents=0,
		)

		with patch("paymob_integration.paymob.inquiry.by_reference") as by_reference:
			processor.process_transaction(parent.name)

		by_reference.assert_not_called()
		parent.reload()
		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(parent.processed, 1)
		self.assertEqual(attempt.state, "Paid")
		self.assertFalse(attempt.needs_human_attention)
		# Never set before a first refund posts — falsy, not literally 0 (`processor` treats it as
		# `attempt.refunded_amount_cents or 0` throughout, never writes a default).
		self.assertFalse(attempt.refunded_amount_cents)
		self.assertEqual(attempt.refund_requested_at, lock)
		self.assertFalse(frappe.db.exists("Paymob Audit Entry", {"paymob_transaction": parent.name}))

	def test_half_refund_parent_resend_fetches_and_posts_the_signed_child(self):
		"""ADR-0034: the parent re-send posts nothing itself. It triggers a Transaction Inquiry
		that fetches the signed child transaction, and that child — stored as its own Paymob
		Transaction row — is what posts the reversal, through the same branch a webhook-delivered
		child already uses.
		"""
		attempt, request = self._paid_attempt()
		charged = transactions.verified_charge(attempt.name)
		before = payment_entry_count()
		attempt.db_set("refund_requested_at", frappe.utils.now_datetime())
		parent = given_transaction(
			"Refund",
			"refund-parent-half-1",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=13778,
		)
		child_obj = _child_obj("refund-child-half-1", charged, 13778, 13778)

		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=child_obj) as by_reference:
			processor.process_transaction(parent.name)

		by_reference.assert_called_once()
		parent.reload()
		attempt.reload()
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(parent.processed, 1)
		self.assertEqual(attempt.state, "Partially Refunded")
		self.assertEqual(attempt.refunded_amount_cents, 13778)
		self.assertIsNone(attempt.refund_requested_at)
		child = frappe.get_doc("Paymob Transaction", "refund-child-half-1:Refund:13778")
		self.assertEqual(child.processed, 1)
		entry = frappe.get_doc(
			"Payment Entry", frappe.get_all("Payment Entry", order_by="creation desc", pluck="name")[0]
		)
		self.assertEqual(entry.paid_amount, 137.78)
		self.assertEqual(child.payment_entry, entry.name)

	def test_second_half_refund_completes_the_reversal(self):
		"""The exact live regression on `ACC-PRQ-2026-00028-1`: two half refunds must produce two
		Payment Entries of 649.50-equivalent size each, never one of the full charge.
		"""
		attempt, request = self._paid_attempt()
		charged = transactions.verified_charge(attempt.name)
		first_parent = given_transaction(
			"Refund",
			"refund-parent-half-2a",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=13778,
		)
		first_child_obj = _child_obj("refund-child-half-2a", charged, 13778, 13778)
		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=first_child_obj):
			processor.process_transaction(first_parent.name)
		before = payment_entry_count()
		attempt.reload()

		second_parent = given_transaction(
			"Refund",
			"refund-parent-half-2b",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)
		second_child_obj = _child_obj("refund-child-half-2b", charged, 13777, 27555)
		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=second_child_obj):
			processor.process_transaction(second_parent.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(attempt.state, "Refunded")
		self.assertEqual(attempt.refunded_amount_cents, 27555)
		entries = frappe.get_all(
			"Payment Entry",
			filters={"payment_type": "Pay", "payment_request": request.name},
			pluck="paid_amount",
		)
		self.assertEqual(len(entries), 2)
		self.assertAlmostEqual(sum(entries), 275.55, places=2)
		# The exact live regression: never a single reversal of the full charge.
		self.assertNotIn(275.55, entries)

	def test_full_refund_parent_resend_fetches_and_posts_the_signed_child(self):
		attempt, request = self._paid_attempt()
		charged = transactions.verified_charge(attempt.name)
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-full",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)
		child_obj = _child_obj("refund-child-full", charged, 27555, 27555)

		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=child_obj):
			processor.process_transaction(parent.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(attempt.state, "Refunded")
		self.assertEqual(attempt.refunded_amount_cents, 27555)
		self.assertFalse(attempt.needs_human_attention)
		self.assertFalse(frappe.db.exists("Paymob Audit Entry", {"paymob_transaction": parent.name}))
		entry = frappe.get_doc(
			"Payment Entry", frappe.get_all("Payment Entry", order_by="creation desc", pluck="name")[0]
		)
		self.assertEqual(entry.payment_type, "Pay")
		self.assertEqual(entry.docstatus, 1)
		self.assertEqual(entry.paid_amount, 275.55)

	def test_duplicate_full_refund_resend_posts_nothing_more(self):
		"""A second parent re-send whose cumulative total matches what the first already posted
		is routine, not a second inquiry: the early `reported <= posted` check short-circuits it
		before `inquiry.by_reference` is ever called again.
		"""
		attempt, request = self._paid_attempt()
		charged = transactions.verified_charge(attempt.name)
		payload = dict(amount_cents=27555, has_parent_transaction=0, refunded_amount_cents=27555)
		first = given_transaction("Refund", "refund-dup-1", attempt.name, request.name, **payload)
		child_obj = _child_obj("refund-dup-child", charged, 27555, 27555)
		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=child_obj):
			processor.process_transaction(first.name)
		before = payment_entry_count()

		second = given_transaction("Refund", "refund-dup-2", attempt.name, request.name, **payload)
		with patch("paymob_integration.paymob.inquiry.by_reference") as by_reference:
			processor.process_transaction(second.name)

		by_reference.assert_not_called()
		self.assertEqual(payment_entry_count(), before)

	def test_inquiry_returning_nothing_holds_for_review(self):
		"""No child transaction exists yet at Paymob (or the inquiry answered 404) — the resend
		alone cannot prove any delta. Held, not posted.
		"""
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-no-child",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=10000,
		)

		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=None):
			processor.process_transaction(parent.name)

		parent.reload()
		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(parent.processed, 1)
		self.assertEqual(attempt.needs_human_attention, 1)
		audit_entry = frappe.db.get_value("Paymob Audit Entry", {"paymob_transaction": parent.name}, "event")
		self.assertEqual(audit_entry, "Refund Requires Review")

	def test_child_whose_delta_contradicts_the_cumulative_total_holds(self):
		"""The returned child is a real, signed child of this attempt, but its amount does not
		reconcile against what Paymob itself reports as the running total — a lost intermediate
		child, or two refunds landing between polls.
		"""
		attempt, request = self._paid_attempt()
		charged = transactions.verified_charge(attempt.name)
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-tampered",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)
		# posted (0) + this child's delta (10000) != reported (27555)
		child_obj = _child_obj("refund-child-tampered", charged, 10000, 27555)

		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=child_obj):
			processor.process_transaction(parent.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.needs_human_attention, 1)

	def test_second_full_refund_resend_after_posted_one_holds(self):
		attempt, request = self._paid_attempt()
		charged = transactions.verified_charge(attempt.name)
		first = given_transaction(
			"Refund",
			"refund-parent-second-1",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)
		first_child_obj = _child_obj("refund-child-second-1", charged, 27555, 27555)
		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=first_child_obj):
			processor.process_transaction(first.name)
		before = payment_entry_count()

		second = given_transaction(
			"Refund",
			"refund-parent-second-2",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=30000,
		)
		# Nothing more was actually refunded at Paymob — the inquiry finds no further child.
		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=None):
			processor.process_transaction(second.name)

		attempt.reload()
		second.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.needs_human_attention, 1)
		self.assertEqual(second.processed, 1)

	def test_child_currency_mismatch_refuses(self):
		"""The currency mismatch check runs on the fetched child, once it is stored and
		reprocessed — never on the parent re-send's own (irrelevant) currency field.
		"""
		attempt, request = self._paid_attempt()
		charged = transactions.verified_charge(attempt.name)
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-currency",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)
		child_obj = _child_obj("refund-child-currency", charged, 27555, 27555, currency="USD")

		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=child_obj):
			processor.process_transaction(parent.name)

		self.assertEqual(payment_entry_count(), before)
		# The mismatch fires while reprocessing the stored *child*, not the parent re-send itself.
		audit_entry = frappe.db.get_value(
			"Paymob Audit Entry", {"attempt": attempt.name}, "event", order_by="creation desc"
		)
		self.assertEqual(audit_entry, "Amount Mismatch")

	def test_no_verified_charge_holds_for_review(self):
		"""Without a verified charge, the child's `parent_transaction` can never be matched — this
		holds for review rather than posting, exactly like an inquiry that finds nothing.
		"""
		attempt, request, invoice = given_attempt(state="Paid", credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-no-charge",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)

		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=None):
			processor.process_transaction(parent.name)

		self.assertEqual(payment_entry_count(), before)
		audit_entry = frappe.db.get_value("Paymob Audit Entry", {"paymob_transaction": parent.name}, "event")
		self.assertEqual(audit_entry, "Refund Requires Review")

	def test_replay_of_stored_live_parent_refund_payload(self):
		"""Rebuilt from the live capital fixture test-510236778:Refund:27555 — the payload that
		originally landed as a stuck Refund Requires Review entry.
		"""
		attempt, request, invoice = given_attempt(credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		success = given_transaction(
			"Success", "test-510236778", attempt.name, request.name, amount_cents=27555
		)
		processor.process_transaction(success.name)
		charged = transactions.verified_charge(attempt.name)
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"test-510236778",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)
		child_obj = _child_obj("test-510236778-child", charged, 27555, 27555)

		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=child_obj):
			processor.process_transaction(parent.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(attempt.state, "Refunded")
		self.assertEqual(attempt.refunded_amount_cents, 27555)

	def test_reprocessing_the_same_parent_resend_is_a_no_op(self):
		attempt, request = self._paid_attempt()
		charged = transactions.verified_charge(attempt.name)
		parent = given_transaction(
			"Refund",
			"refund-parent-reprocess",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=10000,
		)
		child_obj = _child_obj("refund-child-reprocess", charged, 10000, 10000)
		with patch("paymob_integration.paymob.inquiry.by_reference", return_value=child_obj):
			processor.process_transaction(parent.name)
		before = payment_entry_count()

		with patch("paymob_integration.paymob.inquiry.by_reference") as by_reference:
			processor.process_transaction(parent.name)

		by_reference.assert_not_called()
		self.assertEqual(payment_entry_count(), before)

	def test_inquiry_failure_leaves_the_row_unprocessed(self):
		"""A `PaymobError` from the inquiry propagates: nothing posts, the attempt is untouched,
		and the parent row stays `processed = 0` for the next `tasks._sweep_unprocessed_refunds`
		run to retry. A timeout never changes payment state.
		"""
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-inquiry-fails",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=10000,
		)

		with patch(
			"paymob_integration.paymob.inquiry.by_reference",
			side_effect=client.PaymobNetworkError("timed out"),
		):
			with self.assertRaises(client.PaymobNetworkError):
				processor.process_transaction(parent.name)

		parent.reload()
		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(parent.processed, 0)
		self.assertFalse(attempt.needs_human_attention)

	def test_refund_with_no_payment_entry_posts_nothing(self):
		attempt, request, invoice = given_attempt(state="Paid", credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		given_transaction("Success", "refund-unposted-charge", attempt.name, request.name, processed=1)
		before = payment_entry_count()
		refund = given_transaction(
			"Refund",
			"refund-unposted",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=1,
		)

		processor.process_transaction(refund.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.state, "Refunded")
		self.assertFalse(frappe.db.exists("Paymob Audit Entry", {"paymob_transaction": refund.name}))
