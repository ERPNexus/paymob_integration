# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PaymobTransaction(Document):
	def autoname(self):
		if not self.paymob_transaction_id or not self.event_kind:
			frappe.throw(_("A Paymob Transaction needs a transaction ID and an event kind."))
		key = f"{self.paymob_transaction_id}:{self.event_kind}"
		if self.event_kind == "Refund":
			# Paymob resends the same parent transaction id for each cumulative partial refund,
			# with a growing refunded_amount_cents (plans/11-refund-and-void.md). Without the
			# amount in the key, the second partial refund would collide with the first's row
			# and be silently dropped by the dedup constraint instead of recorded.
			key = f"{key}:{self.refunded_amount_cents or 0}"
		self.name = key
