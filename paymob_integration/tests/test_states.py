from frappe.tests.utils import FrappeTestCase

from paymob_integration.paymob import states


class TestStates(FrappeTestCase):
	def test_every_legal_transition(self):
		for current, targets in states.LEGAL.items():
			for target in targets:
				self.assertTrue(states.check(current, target))

	def test_every_known_state_rejects_each_other_known_state(self):
		for current in states.LEGAL:
			for target in states.LEGAL:
				if target in states.LEGAL[current] or target == current:
					continue
				with self.assertRaises(states.IllegalTransition):
					states.check(current, target)

	def test_same_state_is_a_noop(self):
		for state in states.LEGAL:
			self.assertFalse(states.check(state, state))

	def test_expiry_transition_is_legal(self):
		self.assertTrue(states.check("Pending", "Expired"))

	def test_immediate_payment_and_refund_transitions(self):
		for current, target in (
			("Pending", "Paid"),
			("Pending", "Failed"),
			("Failed", "Paid"),
			("Paid", "Partially Refunded"),
			("Paid", "Refunded"),
			("Partially Refunded", "Refunded"),
		):
			self.assertTrue(states.check(current, target))

	def test_retired_states_are_not_legal(self):
		with self.assertRaises(states.IllegalTransition):
			states.check("Pending", "Retired State")

	def test_event_targets(self):
		self.assertEqual(states.target_state("Success"), "Paid")
		self.assertEqual(states.target_state("Decline"), "Failed")
		self.assertIsNone(states.target_state("Unsupported"))
