from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
	create_custom_field(
		"Payment Request",
		{
			"fieldname": "paymob_authorize_only",
			"fieldtype": "Check",
			"label": "Authorize Only (Paymob)",
			"insert_after": "payment_url",
			"depends_on": 'eval:doc.payment_request_type=="Inward"',
		},
	)
