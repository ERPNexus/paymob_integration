from frappe.tests import UnitTestCase

from paymob_integration.paymob import states

ALL_STATES = (
	"Pending",
	"Authorized",
	"Paid",
	"Failed",
	"Expired",
	"Partially Refunded",
	"Refunded",
	"Voided",
)

LEGAL_PAIRS = {
	("Pending", "Paid"),
	("Pending", "Authorized"),
	("Authorized", "Paid"),
	("Authorized", "Voided"),
	("Pending", "Failed"),
	("Pending", "Expired"),
	("Paid", "Partially Refunded"),
	("Paid", "Refunded"),
	("Paid", "Voided"),
	("Partially Refunded", "Refunded"),
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

	def test_refund_target_uses_the_local_total(self):
		self.assertEqual(states.refund_target(10000, 27555), "Partially Refunded")
		self.assertEqual(states.refund_target(27555, 27555), "Refunded")
		self.assertEqual(states.refund_target(30000, 27555), "Refunded")

	def test_pending_has_no_target(self):
		self.assertIsNone(states.target_state("Pending"))

	def test_auth_targets_authorized(self):
		self.assertEqual(states.target_state("Auth"), "Authorized")

	def test_capture_targets_paid(self):
		self.assertEqual(states.target_state("Capture"), "Paid")

	def test_void_targets_voided(self):
		self.assertEqual(states.target_state("Void"), "Voided")
