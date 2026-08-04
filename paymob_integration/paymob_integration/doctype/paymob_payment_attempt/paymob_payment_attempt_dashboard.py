from frappe import _


def get_data():
	return {
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
			{"label": _("Payment"), "items": ["Payment Request", "Payment Entry"]},
			{"label": _("Paymob"), "items": ["Paymob Transaction", "Paymob Audit Entry"]},
		],
	}
