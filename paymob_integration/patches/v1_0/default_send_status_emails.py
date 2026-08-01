import frappe


def execute():
	"""Existing sites predate `send_status_emails`; keep their alerts on rather than off by omission."""
	if frappe.db.get_single_value("Paymob Settings", "send_status_emails") is None:
		frappe.db.set_single_value("Paymob Settings", "send_status_emails", 1)
