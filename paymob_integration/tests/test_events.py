from frappe.tests import UnitTestCase

from paymob_integration.paymob.events import classify_event
from paymob_integration.paymob.transactions import event_key


class TestClassifyEvent(UnitTestCase):
	def test_retired_flags_are_unsupported(self):
		for flag in ("is_voided", "is_capture", "is_auth"):
			self.assertEqual(classify_event({flag: True}), "Unsupported")

	def test_refund_flag_wins_over_success(self):
		# A refund callback also carries success: true — the reversal flag must be read first.
		self.assertEqual(classify_event({"is_refunded": True, "success": True}), "Refund")

	def test_pending_wins_over_success(self):
		# Wallet/kiosk: pending: true, success: true — a settlement follows later for the
		# same transaction id and must not share the Success event_key.
		self.assertEqual(classify_event({"pending": True, "success": True}), "Pending")

	def test_success_flag(self):
		self.assertEqual(classify_event({"success": True}), "Success")

	def test_empty_object_declines(self):
		self.assertEqual(classify_event({}), "Decline")

	def test_success_false_declines(self):
		self.assertEqual(classify_event({"success": False}), "Decline")

	def test_falsy_flags_are_tolerated_not_raised(self):
		obj = {
			"is_voided": False,
			"is_refunded": False,
			"is_capture": False,
			"is_auth": False,
			"pending": False,
			"success": False,
		}
		self.assertEqual(classify_event(obj), "Decline")

	def test_standalone_success_is_a_charge(self):
		obj = {
			"success": True,
			"pending": False,
			"is_auth": False,
			"is_capture": False,
			"is_refunded": False,
			"is_voided": False,
		}
		self.assertEqual(classify_event(obj), "Success")

	def test_retired_subtypes_keep_distinct_dedup_keys(self):
		self.assertNotEqual(
			event_key("123", "Unsupported", unsupported_subtype="Auth"),
			event_key("123", "Unsupported", unsupported_subtype="Capture"),
		)
