from frappe.tests import UnitTestCase

from paymob_integration.paymob import states

ALL_STATES = ("Pending", "Paid", "Failed", "Expired", "Refunded")

LEGAL_PAIRS = {
	("Pending", "Paid"),
	("Pending", "Failed"),
	("Pending", "Expired"),
	("Paid", "Refunded"),
}


class TestCheck(UnitTestCase):
	def test_all_pairs(self):
		for current in ALL_STATES:
			for target in ALL_STATES:
				with self.subTest(current=current, target=target):
					if current == target:
						self.assertFalse(states.check(current, target))
					elif (current, target) in LEGAL_PAIRS:
						self.assertTrue(states.check(current, target))
					else:
						with self.assertRaises(states.IllegalTransition):
							states.check(current, target)

	def test_failed_to_paid_is_illegal(self):
		with self.assertRaises(states.IllegalTransition):
			states.check("Failed", "Paid")

	def test_paid_to_failed_is_illegal(self):
		with self.assertRaises(states.IllegalTransition):
			states.check("Paid", "Failed")


class TestTargetState(UnitTestCase):
	def test_success_targets_paid(self):
		self.assertEqual(states.target_state("Success"), "Paid")

	def test_decline_targets_failed(self):
		self.assertEqual(states.target_state("Decline"), "Failed")

	def test_refund_targets_refunded(self):
		self.assertEqual(states.target_state("Refund"), "Refunded")

	def test_pending_has_no_target(self):
		self.assertIsNone(states.target_state("Pending"))

	def test_auth_has_no_target(self):
		self.assertIsNone(states.target_state("Auth"))

	def test_capture_has_no_target(self):
		self.assertIsNone(states.target_state("Capture"))

	def test_void_has_no_target(self):
		self.assertIsNone(states.target_state("Void"))
