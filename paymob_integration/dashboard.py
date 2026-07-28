from frappe import _


def get_payment_request_dashboard(data):
	data["transactions"].append({"label": _("Paymob"), "items": ["Paymob Payment Attempt"]})
	return data
