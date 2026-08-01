"""Seed editable, opt-out-able Paymob notifications once per site."""

import frappe
from frappe.email.doctype.notification.notification import clear_notification_cache

from paymob_integration import email

PAYMENT_REQUEST_COMPANY = "frappe.db.get_value('Payment Request', doc.payment_request, 'company')"


def seed():
	for spec in _spec():
		if not frappe.db.exists("Notification", spec["name"]):
			frappe.get_doc(spec).insert(ignore_permissions=True)


def sync_enabled(enabled):
	"""Flip `enabled` on the records this app seeded, and only those.

	Named lookups, not a `document_type` filter — a merchant's own Notification on the same
	DocType must never be switched off by a Paymob setting.
	"""
	value = 1 if enabled else 0
	for spec in _spec():
		if frappe.db.exists("Notification", spec["name"]):
			frappe.db.set_value("Notification", spec["name"], "enabled", value, update_modified=False)
	clear_notification_cache()


def refresh_defaults():
	"""Apply the one-time template correction without changing later Desk edits."""
	for spec in _spec():
		if frappe.db.exists("Notification", spec["name"]):
			frappe.db.set_value(
				"Notification",
				spec["name"],
				{"subject": spec["subject"], "message": spec["message"]},
				update_modified=False,
			)


def _spec() -> list[dict]:
	specs = [
		{
			"doctype": "Notification",
			"name": "Paymob Audit Entry Needs Review",
			"document_type": "Paymob Audit Entry",
			"event": "Submit",
			"condition": "doc.needs_action == 1",
			"subject": "{{ _('Paymob payment needs review') }}",
			"message": email.render(
				"{{ _('Paymob payment needs review') }}",
				"{{ _('Action needed') }}",
				email.ERROR,
				"<p>{{ doc.description }}</p><p>{{ _('Payment Request') }}: <strong>{{ doc.payment_request }}</strong></p>",
				PAYMENT_REQUEST_COMPANY,
				"{{ _('Review audit entry') }}",
				"{{ frappe.utils.get_url_to_form('Paymob Audit Entry', doc.name) }}",
				"<p style=\"margin: 16px 0 0;\"><strong>{{ _('Expected') }}:</strong> {{ doc.expected_amount_cents }} {{ doc.expected_currency }}<br><strong>{{ _('Received') }}:</strong> {{ doc.received_amount_cents }} {{ doc.received_currency }}</p>",
			),
			"recipients": [{"receiver_by_role": "Accounts Manager"}, {"receiver_by_role": "System Manager"}],
		},
		*_attempt_specs(),
		{
			"doctype": "Notification",
			"name": "Paymob Refund or Void Activity",
			"document_type": "Paymob Audit Entry",
			"event": "Submit",
			"condition": "doc.event in ('Refund Requested', 'Void Requested', 'Nothing To Reverse')",
			"subject": "{{ _('Paymob refund or void activity') }}",
			"message": email.render(
				"{{ _('Paymob refund or void activity') }}",
				"{{ _('Activity recorded') }}",
				email.NEUTRAL,
				"<p>{{ doc.description }}</p><p>{{ _('Payment Request') }}: <strong>{{ doc.payment_request }}</strong></p>",
				PAYMENT_REQUEST_COMPANY,
				"{{ _('Review audit entry') }}",
				"{{ frappe.utils.get_url_to_form('Paymob Audit Entry', doc.name) }}",
			),
			"recipients": [{"receiver_by_role": "Accounts Manager"}, {"receiver_by_role": "System Manager"}],
		},
		{
			"doctype": "Notification",
			"name": "Paymob Webhook Missed - Poller Recovered",
			"document_type": "Paymob Audit Entry",
			"event": "Submit",
			"condition": "doc.event == 'Poller Recovery'",
			"subject": "{{ _('Paymob poller recovered a payment') }}",
			"message": email.render(
				"{{ _('Paymob poller recovered a payment') }}",
				"{{ _('Recovered') }}",
				email.SUCCESS,
				"<p>{{ doc.description }}</p><p>{{ _('Payment Request') }}: <strong>{{ doc.payment_request }}</strong></p>",
				PAYMENT_REQUEST_COMPANY,
				"{{ _('Review audit entry') }}",
				"{{ frappe.utils.get_url_to_form('Paymob Audit Entry', doc.name) }}",
			),
			"recipients": [{"receiver_by_role": "Accounts Manager"}, {"receiver_by_role": "System Manager"}],
		},
	]
	return [_notification(spec) for spec in specs]


def _notification(spec):
	return {
		"doctype": "Notification",
		"enabled": 1,
		"is_standard": 0,
		"channel": "Email",
		"send_system_notification": 1,
		"condition_type": "Python",
		"message_type": "HTML",
		**spec,
	}


def _attempt_specs():
	return [
		{
			"doctype": "Notification",
			"name": name,
			"document_type": "Paymob Payment Attempt",
			"event": "Value Change",
			"value_changed": "state",
			"condition": condition,
			"subject": subject,
			"message": message,
			"recipients": [{"receiver_by_document_field": "contact_email"}],
		}
		for name, condition, subject, message in [
			(
				"Paymob Payment Received",
				"doc.state == 'Paid'",
				"{{ _('Payment received') }}",
				email.render(
					"{{ _('Payment received') }}",
					"{{ _('Paid') }}",
					email.SUCCESS,
					"<p>{{ _('Your payment has been received.') }}</p>",
					PAYMENT_REQUEST_COMPANY,
				),
			),
			(
				"Paymob Payment Failed",
				"doc.state == 'Failed'",
				"{{ _('Payment failed') }}",
				_retry_message("{{ _('Payment failed') }}", "{{ _('Action needed') }}", email.ERROR),
			),
			(
				"Paymob Payment Link Expired",
				"doc.state == 'Expired'",
				"{{ _('Payment link expired') }}",
				_retry_message("{{ _('Payment link expired') }}", "{{ _('Expired') }}", email.WARNING),
			),
			(
				"Paymob Refund Issued",
				"doc.state in ('Refunded', 'Partially Refunded')",
				"{{ _('Refund issued') }}",
				email.render(
					"{{ _('Refund issued') }}",
					"{{ _('Refunded') }}",
					email.INFO,
					"<p>{{ _('Your refund has been issued.') }}</p>",
					PAYMENT_REQUEST_COMPANY,
				),
			),
		]
	]


def _retry_message(title, status, tone):
	return email.render(
		title,
		status,
		tone,
		"<p>{{ _('This payment did not go through. You can try again.') }}</p>",
		PAYMENT_REQUEST_COMPANY,
		"{{ _('try your payment again') }}",
		"{{ build(doc.payment_request) }}",
	)
