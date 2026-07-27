// Copyright (c) 2026, Abdelrahman Elsayed and contributors
// For license information, please see license.txt

frappe.ui.form.on("Paymob Transaction", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.processed) {
			return;
		}
		frm.add_custom_button(__("Process"), () => {
			frappe.confirm(
				__(
					"Run this transaction through the state machine now instead of waiting for the background job?"
				),
				() => {
					frappe.call({
						method: "paymob_integration.paymob_integration.doctype.paymob_transaction.paymob_transaction.process",
						args: { name: frm.doc.name },
						freeze: true,
						freeze_message: __("Processing..."),
						callback: () => frm.reload_doc(),
					});
				}
			);
		});
	},
});
