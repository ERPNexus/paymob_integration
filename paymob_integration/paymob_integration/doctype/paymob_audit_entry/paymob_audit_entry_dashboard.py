from frappe import _


def get_data():
	return {
		"fieldname": "name",
		"internal_links": {
			"Payment Request": "payment_request",
			"Paymob Payment Attempt": "attempt",
			"Paymob Transaction": "paymob_transaction",
			"Payment Entry": "payment_entry",
		},
		"transactions": [
			{
				"label": _("Paymob"),
				"items": ["Payment Request", "Paymob Payment Attempt", "Paymob Transaction"],
			},
			{"label": _("Accounting"), "items": ["Payment Entry"]},
		],
	}
