from pathlib import Path
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from paymob_integration import notifications, payment_request


class TestNotifications(UnitTestCase):
	def test_catalogue_contains_the_six_editable_alerts(self):
		specs = notifications._spec()
		self.assertEqual(len(specs), 6)
		self.assertTrue(all(spec["event"] in ("Submit", "Value Change") for spec in specs))
		self.assertTrue(all(spec["recipients"] for spec in specs))
		self.assertTrue(all(spec["channel"] == "Email" and spec["message_type"] == "HTML" for spec in specs))
		self.assertNotIn("Paymob Webhook Missed - Poller Recovered", {spec["name"] for spec in specs})
		activity = next(spec for spec in specs if spec["name"] == "Paymob Refund Activity")
		self.assertEqual(activity["condition"], "doc.event == 'Refund Requested'")

	def test_design_rule_is_registered(self):
		root = Path(__file__).parents[2]
		self.assertIn("[design.md](design.md)", (root / "rules" / "README.md").read_text())
		self.assertTrue((root / "rules" / "design.md").is_file())

	def test_email_templates_render_status_cta_and_rtl_safe_structure(self):
		doc = frappe._dict(
			name="PMB-AUD-2026-00001",
			description="The payment needs review.",
			payment_request="ACC-PR-0001",
			expected_amount_cents=27555,
			expected_currency="EGP",
			received_amount_cents=27000,
			received_currency="EGP",
		)
		payment_request_doc = frappe._dict(company="Acme Trading")
		failed = next(spec for spec in notifications._spec() if spec["name"] == "Paymob Payment Failed")
		rendered = frappe.render_template(
			failed["message"],
			{
				"doc": doc,
				"build": lambda _: "https://site.test/paymob-pay?signed",
				"frappe": frappe._dict(db=frappe._dict(get_value=lambda *_: payment_request_doc.company)),
			},
		)

		self.assertIn("Payment failed", rendered)
		self.assertIn("Action needed", rendered)
		self.assertIn("https://site.test/paymob-pay?signed", rendered)
		self.assertIn(payment_request_doc.company, rendered)
		self.assertNotIn("automated message from Paymob", rendered)
		self.assertIn('dir="', rendered)
		self.assertIn("max-width: 600px", rendered)
		self.assertIn("{{ _(", failed["message"])
		self.assertIn("Payment link ready", payment_request.DEFAULT_MESSAGE)

		language = frappe.local.lang
		try:
			frappe.local.lang = "ar"
			rtl = frappe.render_template(
				payment_request.DEFAULT_MESSAGE,
				{"doc": payment_request_doc, "payment_url": "https://site.test/pay"},
			)
		finally:
			frappe.local.lang = language

		self.assertIn('dir="rtl"', rtl)
		self.assertIn("رابط الدفع جاهز", rtl)

	def test_templates_use_the_payment_request_company(self):
		company = "Acme Trading"
		for doctype in ("Payment Request", "Paymob Payment Attempt", "Paymob Audit Entry"):
			message = (
				payment_request.DEFAULT_MESSAGE
				if doctype == "Payment Request"
				else next(spec for spec in notifications._spec() if spec["document_type"] == doctype)[
					"message"
				]
			)
			rendered = frappe.render_template(
				message,
				{
					"doc": frappe._dict(company=company, payment_request="ACC-PR-0001"),
					"payment_url": "https://site.test/pay",
					"frappe": frappe._dict(
						db=frappe._dict(get_value=lambda *_: company),
						utils=frappe._dict(get_url_to_form=lambda *_: "https://site.test/form"),
					),
				},
			)
			self.assertIn(company, rendered)
			self.assertNotIn("automated message from Paymob", rendered)

	def test_seed_creates_only_missing_notifications(self):
		created = Mock()
		with (
			patch("paymob_integration.notifications._spec", return_value=[{"name": "new"}, {"name": "kept"}]),
			patch("paymob_integration.notifications.frappe.db.exists", side_effect=[False, True]),
			patch("paymob_integration.notifications.frappe.get_doc", return_value=created),
		):
			notifications.seed()

		created.insert.assert_called_once_with(ignore_permissions=True)

	def test_refresh_defaults_updates_each_existing_notification(self):
		specs = notifications._spec()
		with (
			patch("paymob_integration.notifications.frappe.db.exists", return_value=True),
			patch("paymob_integration.notifications.frappe.db.set_value") as set_value,
		):
			notifications.refresh_defaults()

		self.assertEqual(set_value.call_count, len(specs))
		for spec in specs:
			set_value.assert_any_call(
				"Notification",
				spec["name"],
				{"subject": spec["subject"], "message": spec["message"]},
				update_modified=False,
			)

	def test_sync_enabled_flips_only_the_seeded_records(self):
		specs = notifications._spec()
		for enabled, expected in ((0, 0), (1, 1)):
			with (
				patch("paymob_integration.notifications.frappe.db.exists", return_value=True),
				patch("paymob_integration.notifications.frappe.db.set_value") as set_value,
				patch("paymob_integration.notifications.clear_notification_cache") as clear_cache,
			):
				notifications.sync_enabled(enabled)

			self.assertEqual(set_value.call_count, len(specs))
			self.assertEqual(
				[call.args[1] for call in set_value.call_args_list], [spec["name"] for spec in specs]
			)
			for spec in specs:
				set_value.assert_any_call(
					"Notification", spec["name"], "enabled", expected, update_modified=False
				)
			clear_cache.assert_called_once_with()

	def test_sync_enabled_skips_a_notification_the_merchant_deleted(self):
		with (
			patch("paymob_integration.notifications._spec", return_value=[{"name": "gone"}]),
			patch("paymob_integration.notifications.frappe.db.exists", return_value=False),
			patch("paymob_integration.notifications.frappe.db.set_value") as set_value,
			patch("paymob_integration.notifications.clear_notification_cache"),
		):
			notifications.sync_enabled(0)

		set_value.assert_not_called()

	def test_settings_save_applies_the_status_email_toggle(self):
		settings = frappe.get_doc("Paymob Settings")
		self.assertEqual(settings.meta.get_field("send_status_emails").default, "1")
		with patch("paymob_integration.notifications.sync_enabled") as sync_enabled:
			settings.send_status_emails = 0
			settings.on_update()

		sync_enabled.assert_called_once_with(0)
