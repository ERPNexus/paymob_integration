"""Tests for paymob.tasks.reconcile_pending_attempts (Phase 10). `client.request` is the only
patched seam — auth-token fetches and Transaction Inquiry POSTs both flow through it, so the
fake below dispatches by URL to keep the two concerns distinguishable in assertions.
"""

from unittest.mock import Mock, patch

import frappe

from paymob_integration import tasks
from paymob_integration.paymob import amounts, auth, client
from paymob_integration.tests.helpers import (
	NoCommitIntegrationTestCase,
	cleanup_fixture,
	given_attempt,
	given_transaction,
	payment_entry_count,
)


def _clearing_account():
	company = frappe.defaults.get_global_default("company")
	return frappe.get_cached_value("Company", company, "default_cash_account")


def _credentials():
	row = Mock()
	row.country = "Egypt"
	row.currency = "EGP"
	row.mode = "Test"
	row.base_url = "https://accept.paymobsolutions.com"
	row.get_password.return_value = "api-key-value"
	row.payment_account = _clearing_account()
	return row


def _transaction_obj(txn_id, amount_cents=27555, currency="EGP", **overrides):
	return {
		"id": txn_id,
		"amount_cents": amount_cents,
		"currency": currency,
		"success": True,
		"pending": False,
		"is_refunded": False,
		"is_voided": False,
		"is_capture": False,
		"is_auth": False,
		**overrides,
	}


class _FakeClient:
	"""Routes `client.request` calls by URL. Token fetches always succeed with a fresh,
	incrementing token so a test can prove `force_refresh` actually changed the Bearer header.
	Inquiry POSTs are answered from a queue: each entry is either a transaction object to return
	or an exception instance to raise.
	"""

	def __init__(self, inquiry_responses=None):
		self._inquiry_responses = list(inquiry_responses or [])
		self.inquiry_calls = []  # Authorization header seen on each inquiry POST
		self.token_calls = 0

	def __call__(self, method, url, *, headers=None, json_body=None, timeout=None):
		if url.endswith("/api/auth/tokens"):
			self.token_calls += 1
			return {"token": f"token-{self.token_calls}"}
		assert tasks.INQUIRY_PATH in url
		self.inquiry_calls.append(headers.get("Authorization"))
		response = self._inquiry_responses.pop(0)
		if isinstance(response, Exception):
			raise response
		return response


def _forget_transaction(txn_id):
	frappe.db.delete("Paymob Transaction", {"paymob_transaction_id": txn_id})
	frappe.db.delete("Paymob Audit Entry", {"paymob_transaction_id": txn_id})


class TestReconciliation(NoCommitIntegrationTestCase):
	def setUp(self):
		self.settings = frappe._dict(
			enabled=1,
			stale_pending_minutes=0,
			reconcile_batch_size=50,
			intention_expiration_seconds=3600,
		)
		settings_patcher = patch(
			"paymob_integration.paymob.settings.get_settings", side_effect=lambda: self.settings
		)
		settings_patcher.start()
		self.addCleanup(settings_patcher.stop)

		credentials_patcher = patch(
			"paymob_integration.paymob.settings.get_credential_set", return_value=_credentials()
		)
		credentials_patcher.start()
		self.addCleanup(credentials_patcher.stop)

		frappe.cache().delete_value(auth.cache_key(_credentials()))

	def _given_attempt(self, expires_at=None):
		attempt, payment_request, invoice = given_attempt(credentials=_credentials())
		if expires_at is not None:
			attempt.db_set("expires_at", expires_at)
			attempt.reload()
		self.addCleanup(cleanup_fixture, attempt.name, payment_request.name, invoice.name)
		return attempt, payment_request, invoice

	def _patched_client(self, inquiry_responses=None):
		fake = _FakeClient(inquiry_responses)
		patcher = patch("paymob_integration.tasks.client.request", side_effect=fake)
		patcher.start()
		self.addCleanup(patcher.stop)
		return fake

	# -- 401 handling ------------------------------------------------------------------------

	def test_401_refreshes_the_token_and_retries_once(self):
		attempt, _payment_request, _invoice = self._given_attempt()
		fake = self._patched_client(
			[
				client.PaymobAPIError("unauthorized", status_code=401),
				client.PaymobAPIError("not found", status_code=404),
			]
		)

		tasks.reconcile_pending_attempts()

		self.assertEqual(len(fake.inquiry_calls), 2)
		self.assertNotEqual(fake.inquiry_calls[0], fake.inquiry_calls[1])
		attempt.reload()
		self.assertEqual(attempt.state, "Pending")
		self.assertIsNotNone(attempt.last_polled_at)

	def test_a_second_401_is_not_retried_again(self):
		attempt, _payment_request, _invoice = self._given_attempt()
		fake = self._patched_client(
			[
				client.PaymobAPIError("unauthorized", status_code=401),
				client.PaymobAPIError("unauthorized", status_code=401),
			]
		)

		tasks.reconcile_pending_attempts()

		self.assertEqual(len(fake.inquiry_calls), 2)
		attempt.reload()
		self.assertEqual(attempt.state, "Pending")
		self.assertEqual(frappe.db.count("Paymob Transaction", {"attempt": attempt.name}), 0)

	# -- network / server errors --------------------------------------------------------------

	def test_timeout_changes_nothing(self):
		attempt, _payment_request, _invoice = self._given_attempt()
		before_pe = payment_entry_count()
		self._patched_client([client.PaymobNetworkError("timed out")])

		tasks.reconcile_pending_attempts()

		attempt.reload()
		self.assertEqual(attempt.state, "Pending")
		self.assertEqual(frappe.db.count("Paymob Transaction", {"attempt": attempt.name}), 0)
		self.assertEqual(payment_entry_count(), before_pe)
		self.assertIsNotNone(attempt.last_polled_at)

	def test_5xx_leaves_the_attempt_for_the_next_run(self):
		attempt, _payment_request, _invoice = self._given_attempt()
		before_pe = payment_entry_count()
		self._patched_client([client.PaymobAPIError("bad gateway", status_code=502)])

		tasks.reconcile_pending_attempts()

		attempt.reload()
		self.assertEqual(attempt.state, "Pending")
		self.assertEqual(frappe.db.count("Paymob Transaction", {"attempt": attempt.name}), 0)
		self.assertEqual(payment_entry_count(), before_pe)
		self.assertIsNotNone(attempt.last_polled_at)

	def test_a_network_failure_never_expires_an_attempt(self):
		past = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-1)
		attempt, _payment_request, _invoice = self._given_attempt(expires_at=past)
		self._patched_client([client.PaymobNetworkError("timed out")])

		tasks.reconcile_pending_attempts()

		attempt.reload()
		self.assertEqual(attempt.state, "Pending")
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"attempt": attempt.name}), 0)

	# -- expiry --------------------------------------------------------------------------------

	def test_past_expiry_with_no_transaction_expires(self):
		past = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-1)
		attempt, _payment_request, _invoice = self._given_attempt(expires_at=past)
		before_pe = payment_entry_count()
		self._patched_client([client.PaymobAPIError("not found", status_code=404)])

		tasks.reconcile_pending_attempts()

		attempt.reload()
		self.assertEqual(attempt.state, "Expired")
		entries = frappe.get_all("Paymob Audit Entry", filters={"attempt": attempt.name}, fields=["event"])
		self.assertEqual([e.event for e in entries], ["Attempt Expired"])
		self.assertEqual(payment_entry_count(), before_pe)

	def test_not_yet_expired_stays_pending(self):
		future = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=1)
		attempt, _payment_request, _invoice = self._given_attempt(expires_at=future)
		self._patched_client([client.PaymobAPIError("not found", status_code=404)])

		tasks.reconcile_pending_attempts()

		attempt.reload()
		self.assertEqual(attempt.state, "Pending")
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"attempt": attempt.name}), 0)

	# -- selection -------------------------------------------------------------------------------

	def test_batch_size_is_bounded(self):
		self._given_attempt()
		self._given_attempt()
		self._given_attempt()
		self.settings.reconcile_batch_size = 2
		fake = self._patched_client([client.PaymobAPIError("not found", status_code=404) for _ in range(2)])

		tasks.reconcile_pending_attempts()

		self.assertEqual(len(fake.inquiry_calls), 2)

	def test_selection_skips_fresh_and_settled_attempts(self):
		self.settings.stale_pending_minutes = 999999  # cutoff far in the past: nothing is stale
		self._given_attempt()  # fresh Pending attempt
		attempt, payment_request, invoice = given_attempt(state="Paid", credentials=_credentials())
		self.addCleanup(cleanup_fixture, attempt.name, payment_request.name, invoice.name)
		fake = self._patched_client([])

		tasks.reconcile_pending_attempts()

		self.assertEqual(fake.token_calls, 0)
		self.assertEqual(len(fake.inquiry_calls), 0)

	# -- recovery hand-off -----------------------------------------------------------------------

	def test_lost_webhook_is_recovered(self):
		attempt, payment_request, invoice = self._given_attempt()
		before_pe = payment_entry_count()
		self._patched_client([_transaction_obj("990101")])
		self.addCleanup(_forget_transaction, "990101")

		tasks.reconcile_pending_attempts()

		attempt.reload()
		invoice.reload()
		payment_request.reload()
		txn = frappe.get_doc("Paymob Transaction", "990101:Success")
		self.assertEqual(txn.source, "Inquiry")
		self.assertEqual(txn.hmac_verified, 0)
		self.assertEqual(txn.processed, 1)
		self.assertEqual(frappe.db.count("Paymob Transaction", {"paymob_transaction_id": "990101"}), 1)

		self.assertEqual(payment_entry_count(), before_pe + 1)
		self.assertTrue(attempt.payment_entry)
		payment_entry = frappe.get_doc("Payment Entry", attempt.payment_entry)
		reference = payment_entry.references[0]
		self.assertEqual(reference.reference_name, invoice.name)
		self.assertEqual(
			payment_entry.paid_amount, float(amounts.from_minor_units(txn.amount_cents, txn.currency))
		)
		self.assertEqual(payment_request.status, "Paid")
		self.assertEqual(invoice.outstanding_amount, 0)

		self.assertEqual(attempt.state, "Paid")
		self.assertIsNotNone(attempt.last_polled_at)

		entries = frappe.get_all("Paymob Audit Entry", filters={"attempt": attempt.name}, fields=["event"])
		self.assertEqual([e.event for e in entries], ["Poller Recovery"])

	def test_a_stored_but_unprocessed_duplicate_is_still_recovered(self):
		# The webhook durably stored the row (ADR-0007) but its enqueue/worker crashed before
		# process_transaction marked it processed. The inquiry finds the same transaction id and
		# transactions.store returns None (dedup), but this pass must not treat that as "nothing
		# to do" -- the real payment would otherwise stay Pending forever.
		attempt, payment_request, invoice = self._given_attempt()
		before_pe = payment_entry_count()
		given_transaction("Success", "990102", attempt=attempt.name, payment_request=payment_request.name)
		self.addCleanup(_forget_transaction, "990102")
		self._patched_client([_transaction_obj("990102")])

		tasks.reconcile_pending_attempts()

		attempt.reload()
		invoice.reload()
		self.assertEqual(attempt.state, "Paid")
		self.assertEqual(payment_entry_count(), before_pe + 1)
		self.assertEqual(frappe.db.count("Paymob Transaction", {"paymob_transaction_id": "990102"}), 1)
		txn = frappe.get_doc("Paymob Transaction", "990102:Success")
		self.assertEqual(txn.processed, 1)
		self.assertEqual(txn.source, "Webhook")  # the existing row is reused, not overwritten
		entries = frappe.get_all("Paymob Audit Entry", filters={"attempt": attempt.name}, fields=["event"])
		self.assertEqual([e.event for e in entries], ["Poller Recovery"])

	def test_an_already_processed_duplicate_is_a_no_op(self):
		attempt, payment_request, _invoice = self._given_attempt()
		before_pe = payment_entry_count()
		given_transaction(
			"Success",
			"990103",
			attempt=attempt.name,
			payment_request=payment_request.name,
			processed=1,
		)
		self.addCleanup(_forget_transaction, "990103")
		self._patched_client([_transaction_obj("990103")])

		tasks.reconcile_pending_attempts()

		attempt.reload()
		self.assertEqual(attempt.state, "Pending")
		self.assertEqual(payment_entry_count(), before_pe)
		self.assertEqual(frappe.db.count("Paymob Transaction", {"paymob_transaction_id": "990103"}), 1)
		self.assertEqual(frappe.db.count("Paymob Audit Entry", {"attempt": attempt.name}), 0)
		self.assertIsNotNone(attempt.last_polled_at)

	# -- missing credentials -----------------------------------------------------------------

	def test_missing_credentials_for_one_attempt_does_not_abort_the_batch(self):
		# frappe.throw inside settings.get_credential_set raises ValidationError, not
		# client.PaymobError. Left uncaught it would propagate out of `_reconcile` and abort the
		# whole batch loop instead of just this attempt.
		stale_attempt, _pr1, _inv1 = self._given_attempt()
		fresh_attempt, _pr2, _inv2 = self._given_attempt()
		fake = self._patched_client([client.PaymobAPIError("not found", status_code=404)])

		credentials_patcher = patch(
			"paymob_integration.paymob.settings.get_credential_set",
			side_effect=[frappe.ValidationError("no credentials configured"), _credentials()],
		)
		credentials_patcher.start()
		self.addCleanup(credentials_patcher.stop)

		tasks.reconcile_pending_attempts()

		stale_attempt.reload()
		fresh_attempt.reload()
		self.assertEqual(len(fake.inquiry_calls), 1)  # only the second attempt reached Paymob
		self.assertEqual(stale_attempt.state, "Pending")
		self.assertIsNotNone(stale_attempt.last_polled_at)
		self.assertIsNotNone(fresh_attempt.last_polled_at)
