// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Paymob Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.prompt(
				[
					{
						fieldname: "country",
						fieldtype: "Data",
						label: __("Country"),
						reqd: 1,
					},
					{
						fieldname: "currency",
						fieldtype: "Link",
						options: "Currency",
						label: __("Currency"),
						reqd: 1,
					},
				],
				({ country, currency }) => {
					frappe.call({
						method: "paymob_integration.paymob_integration.doctype.paymob_settings.paymob_settings.test_connection",
						args: { country, currency },
						freeze: true,
						freeze_message: __("Contacting Paymob..."),
						callback: ({ message }) => {
							frappe.msgprint({
								title: __("Paymob"),
								message: message.message,
								indicator: "green",
							});
						},
					});
				},
				__("Test Connection"),
				__("Test")
			);
		});
	},
});
