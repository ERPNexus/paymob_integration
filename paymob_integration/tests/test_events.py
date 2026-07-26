from frappe.tests import UnitTestCase

from paymob_integration.paymob.events import classify_event


class TestClassifyEvent(UnitTestCase):
	def test_void_flag_wins(self):
		self.assertEqual(classify_event({"is_voided": True}), "Void")

	def test_refund_flag_wins_over_success(self):
		# A refund callback also carries success: true — the reversal flag must be read first.
		self.assertEqual(classify_event({"is_refunded": True, "success": True}), "Refund")

	def test_capture_flag(self):
		self.assertEqual(classify_event({"is_capture": True}), "Capture")

	def test_auth_flag(self):
		self.assertEqual(classify_event({"is_auth": True}), "Auth")

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
