from unittest import TestCase

from paymob_integration.paymob_integration.doctype.paymob_payment_attempt.paymob_payment_attempt_dashboard import (
	get_data,
)


class TestPaymentAttemptDashboard(TestCase):
	def test_connections_use_attempt_links(self):
		self.assertEqual(
			get_data(),
			{
				"fieldname": "name",
				"internal_links": {
					"Payment Request": "payment_request",
					"Payment Entry": "payment_entry",
				},
				"non_standard_fieldnames": {
					"Paymob Transaction": "attempt",
					"Paymob Audit Entry": "attempt",
				},
				"transactions": [
					{"label": "Payment", "items": ["Payment Request", "Payment Entry"]},
					{"label": "Paymob", "items": ["Paymob Transaction", "Paymob Audit Entry"]},
				],
			},
		)
