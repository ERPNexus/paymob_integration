"""`transactions.redact` decides what evidence survives into `raw_payload`. Both directions
matter: customer identity and card data must never be stored (rules/stored-payment-data.md), and
the fields a refund decision turns on must be visible to the human reviewing the row.

The payload below mirrors the shape of a real Paymob child refund transaction — the full
179-path capture is catalogued in docs/reference/paymob-payload.md.
"""

import unittest

from paymob_integration.paymob import transactions

REAL_SHAPE = {
	"id": 511470147,
	"amount_cents": 64950,
	"currency": "EGP",
	"success": True,
	"is_refund": True,
	"is_refunded": False,
	"has_parent_transaction": True,
	"parent_transaction": 511436444,
	"refunded_amount_cents": 0,
	"updated_at": "2026-08-08T13:40:43.772950",
	"order": {
		"id": 583051381,
		"merchant_order_id": "ACC-PRQ-2026-00028-1",
		"amount_cents": 129900,
		"paid_amount_cents": 129900,
		"payment_status": "PAID",
		"merchant": {"company_name": "Merchant Co", "city": "Cairo"},
		"shipping_data": {"first_name": "Ahmed", "email": "customer@example.com", "phone_number": "0100"},
	},
	"source_data": {"pan": "0007", "type": "card", "sub_type": "MasterCard"},
	"data": {"card_num": "222300xxxxxx0007", "merchant": "TESTMERCH_C_25P"},
	"billing_data": {"email": "customer@example.com"},
}


class TestRedact(unittest.TestCase):
	def test_refund_evidence_survives(self):
		"""The number a refund posts from must be in the blob a human reviews, not only in its
		own column — the gap that made PMB-AUD-2026-00462 unreadable.
		"""
		stored = transactions.redact(REAL_SHAPE)

		self.assertEqual(stored["refunded_amount_cents"], 0)
		self.assertTrue(stored["is_refund"])
		self.assertEqual(stored["parent_transaction"], 511436444)
		self.assertEqual(stored["order"]["paid_amount_cents"], 129900)

	def test_identity_and_card_data_never_stored(self):
		stored = transactions.redact(REAL_SHAPE)

		self.assertNotIn("billing_data", stored)
		self.assertNotIn("data", stored)
		self.assertNotIn("merchant", stored["order"])
		self.assertNotIn("shipping_data", stored["order"])
		# source_data.pan is Paymob's last-four, not a real PAN — allowed, unlike data.card_num.
		self.assertEqual(stored["source_data"], {"pan": "0007", "type": "card", "sub_type": "MasterCard"})
