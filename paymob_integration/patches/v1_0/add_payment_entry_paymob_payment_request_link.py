from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""A refund Payment Entry deliberately carries no `references` row (ERPNext validates any
	allocation against the referenced document's outstanding balance, which is 0 once the
	Payment Request is fully paid — a reversal would always fail that check).

	The Connections tab's own count/list query falls back to the *default* fieldname
	`payment_request` declared in ERPNext's `payment_request_dashboard.py` whenever a doctype
	has no `non_standard_fieldnames` override — so the field must be named exactly that (not a
	`paymob_`-prefixed one) to be picked up. Payment Entry's own controller never reads
	`self.payment_request` on the parent doc (only on rows of its `references` child table), so
	the name is free to use at the top level.
	"""
	create_custom_fields(
		{
			"Payment Entry": [
				{
					"fieldname": "payment_request",
					"fieldtype": "Link",
					"options": "Payment Request",
					"label": "Payment Request",
					"insert_after": "reference_date",
					"read_only": 1,
					"no_copy": 1,
				}
			]
		}
	)
