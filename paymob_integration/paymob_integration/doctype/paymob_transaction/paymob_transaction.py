# Copyright (c) 2026, Abdelrahman Elsayed and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from paymob_integration.paymob import processor


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


@frappe.whitelist()
def process(name):
	"""Manual rescue button for a row stuck at `processed = 0`. Permission comes from the
	DocType's own `read` row (paymob_transaction.json) rather than a hardcoded role list, so
	the two never drift apart — there is no separate write permission on an append-only event
	log. Calls the same idempotent consumer the webhook enqueues (ADR-0013), never Paymob's API,
	so re-running it on an already-processed row is a no-op rather than a duplicate side effect.
	"""
	frappe.get_doc("Paymob Transaction", name).check_permission("read")
	processor.process_transaction(name)
