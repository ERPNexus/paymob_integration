"""Verified reversal callbacks create on-account Payment Entries exactly once."""

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
		success = given_transaction("Success", "refund-success", attempt.name, request.name)
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

	def test_parent_resend_ahead_of_posted_refunds_is_audited(self):
		"""Paymob's cumulative total on the parent re-send outrunning what this app has actually
		posted means a refund happened at Paymob that never reached the ledger (the child
		transaction is missing). ADR-0017: the unsigned resend cannot post money, but it must not
		vanish silently either — hold it for a human.
		"""
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent",
			attempt.name,
			request.name,
			amount_cents=10000,
			has_parent_transaction=0,
			refunded_amount_cents=10000,
		)

		processor.process_transaction(parent.name)

		parent.reload()
		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(parent.processed, 1)
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(attempt.needs_human_attention, 1)
		audit_entry = frappe.db.get_value(
			"Paymob Audit Entry",
			{"paymob_transaction": parent.name},
			["event", "needs_action", "expected_amount_cents", "received_amount_cents"],
			as_dict=True,
		)
		self.assertEqual(audit_entry.event, "Refund Requires Review")
		self.assertEqual(audit_entry.needs_action, 1)
		self.assertEqual(audit_entry.expected_amount_cents, 0)
		self.assertEqual(audit_entry.received_amount_cents, 10000)

	def test_routine_parent_resend_with_matching_total_is_quiet(self):
		"""The parent re-send arrives on every refund, signed or not. When Paymob's cumulative
		total already matches what this app posted, it is routine bookkeeping — no audit entry,
		no flag, just marked processed.
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

		processor.process_transaction(parent.name)

		parent.reload()
		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(parent.processed, 1)
		self.assertEqual(attempt.state, "Paid")
		self.assertFalse(attempt.needs_human_attention)
		self.assertEqual(attempt.refunded_amount_cents, 0)
		self.assertEqual(attempt.refund_requested_at, lock)
		self.assertFalse(frappe.db.exists("Paymob Audit Entry", {"paymob_transaction": parent.name}))

	def test_full_refund_from_parent_resend_posts(self):
		"""ADR-0032: a parent re-send whose signed amount_cents matches the whole charge, with
		Paymob's cumulative total agreeing and nothing posted yet, is the only shape a standalone
		card refund ever takes (no child transaction is ever sent) — it posts from the signed
		amount_cents, not the unsigned refunded_amount_cents.
		"""
		attempt, request = self._paid_attempt()
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
		"""Same payload twice collides on event_key (transactions.event_key suffixes Refund keys
		with refunded_amount_cents) before it ever reaches the processor a second time.
		"""
		attempt, request = self._paid_attempt()
		payload = dict(
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)
		first = given_transaction("Refund", "refund-dup-1", attempt.name, request.name, **payload)
		processor.process_transaction(first.name)
		before = payment_entry_count()

		second = given_transaction("Refund", "refund-dup-2", attempt.name, request.name, **payload)
		processor.process_transaction(second.name)

		self.assertEqual(payment_entry_count(), before)

	def test_partial_refund_from_parent_resend_still_holds(self):
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-partial",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=10000,
		)

		processor.process_transaction(parent.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.needs_human_attention, 1)
		self.assertTrue(frappe.db.exists("Paymob Audit Entry", {"paymob_transaction": parent.name}))

	def test_tampered_total_on_parent_resend_holds(self):
		"""refunded_amount_cents > amount_cents cannot pass the full_refund equality check and
		cannot inflate a posting.
		"""
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-tampered",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=99999,
		)

		processor.process_transaction(parent.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.needs_human_attention, 1)

	def test_second_full_refund_resend_after_posted_one_holds(self):
		attempt, request = self._paid_attempt()
		first = given_transaction(
			"Refund",
			"refund-parent-second-1",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)
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
		processor.process_transaction(second.name)

		attempt.reload()
		second.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.needs_human_attention, 1)
		self.assertEqual(second.processed, 1)

	def test_full_refund_currency_mismatch_refuses(self):
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"refund-parent-currency",
			attempt.name,
			request.name,
			amount_cents=27555,
			currency="USD",
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)

		processor.process_transaction(parent.name)

		self.assertEqual(payment_entry_count(), before)
		audit_entry = frappe.db.get_value("Paymob Audit Entry", {"paymob_transaction": parent.name}, "event")
		self.assertEqual(audit_entry, "Amount Mismatch")

	def test_full_refund_with_no_verified_charge_refuses(self):
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

		processor.process_transaction(parent.name)

		self.assertEqual(payment_entry_count(), before)
		audit_entry = frappe.db.get_value("Paymob Audit Entry", {"paymob_transaction": parent.name}, "event")
		self.assertEqual(audit_entry, "Amount Mismatch")

	def test_replay_of_stored_live_parent_refund_payload(self):
		"""Rebuilt from the live capital fixture 510236778:Refund:49900 — the payload that
		originally landed as a stuck Refund Requires Review entry.
		"""
		attempt, request, invoice = given_attempt(credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, request.name, invoice.name)
		success = given_transaction("Success", "510236778", attempt.name, request.name, amount_cents=49900)
		processor.process_transaction(success.name)
		before = payment_entry_count()
		parent = given_transaction(
			"Refund",
			"510236778",
			attempt.name,
			request.name,
			amount_cents=49900,
			has_parent_transaction=0,
			refunded_amount_cents=49900,
		)

		processor.process_transaction(parent.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(attempt.state, "Refunded")
		self.assertEqual(attempt.refunded_amount_cents, 49900)

	def test_partial_refund_from_recorded_request_posts(self):
		"""ADR-0033: the locally recorded `refund_requested_cents` — not the unsigned cumulative
		field — drives a partial refund posted from a parent re-send.
		"""
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		attempt.db_set({"refund_requested_at": frappe.utils.now_datetime(), "refund_requested_cents": 10000})
		parent = given_transaction(
			"Refund",
			"refund-parent-partial-recorded",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=10000,
		)

		processor.process_transaction(parent.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(attempt.state, "Partially Refunded")
		self.assertEqual(attempt.refunded_amount_cents, 10000)
		self.assertIsNone(attempt.refund_requested_at)
		self.assertIsNone(attempt.refund_requested_cents)
		entry = frappe.get_doc(
			"Payment Entry", frappe.get_all("Payment Entry", order_by="creation desc", pluck="name")[0]
		)
		self.assertEqual(entry.paid_amount, 100)

	def test_second_partial_refund_from_recorded_request_completes_it(self):
		attempt, request = self._paid_attempt()
		attempt.db_set({"refund_requested_at": frappe.utils.now_datetime(), "refund_requested_cents": 10000})
		first = given_transaction(
			"Refund",
			"refund-parent-partial-1",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=10000,
		)
		processor.process_transaction(first.name)
		before = payment_entry_count()
		attempt.reload()
		attempt.db_set({"refund_requested_at": frappe.utils.now_datetime(), "refund_requested_cents": 17555})
		second = given_transaction(
			"Refund",
			"refund-parent-partial-2",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=27555,
		)

		processor.process_transaction(second.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before + 1)
		self.assertEqual(attempt.state, "Refunded")
		self.assertEqual(attempt.refunded_amount_cents, 27555)
		self.assertIsNone(attempt.refund_requested_at)

	def test_mismatched_cumulative_against_recorded_request_still_holds(self):
		attempt, request = self._paid_attempt()
		before = payment_entry_count()
		attempt.db_set({"refund_requested_at": frappe.utils.now_datetime(), "refund_requested_cents": 10000})
		parent = given_transaction(
			"Refund",
			"refund-parent-partial-mismatch",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=15000,
		)

		processor.process_transaction(parent.name)

		attempt.reload()
		self.assertEqual(payment_entry_count(), before)
		self.assertEqual(attempt.needs_human_attention, 1)
		self.assertIsNone(attempt.refund_requested_at)
		self.assertIsNone(attempt.refund_requested_cents)

	def test_reprocessing_the_same_partial_refund_row_is_a_no_op(self):
		attempt, request = self._paid_attempt()
		attempt.db_set({"refund_requested_at": frappe.utils.now_datetime(), "refund_requested_cents": 10000})
		parent = given_transaction(
			"Refund",
			"refund-parent-partial-reprocess",
			attempt.name,
			request.name,
			amount_cents=27555,
			has_parent_transaction=0,
			refunded_amount_cents=10000,
		)
		processor.process_transaction(parent.name)
		before = payment_entry_count()

		processor.process_transaction(parent.name)

		self.assertEqual(payment_entry_count(), before)

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
