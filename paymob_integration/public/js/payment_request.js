frappe.ui.form.on("Payment Request", {
	refresh(frm) {
		if (
			frm.doc.docstatus !== 1 ||
			frm.doc.payment_request_type !== "Inward" ||
			["Paid", "Cancelled"].includes(frm.doc.status)
		)
			return;

		frm.add_custom_button(__("Pay with Paymob"), () => {
			// Open the tab inside the click gesture; browsers block window.open()
			// called later from an async callback. Navigate it once the URL arrives.
			const checkout_tab = window.open("", "_blank");

			frappe.call({
				method: "paymob_integration.api.start_checkout",
				args: { payment_request: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating a Paymob checkout..."),
				callback: ({ message }) => {
					if (!message?.checkout_url) return;
					if (checkout_tab) {
						checkout_tab.location = message.checkout_url;
					} else {
						frappe.msgprint({
							title: __("Popup Blocked"),
							message: __("Your browser blocked the checkout window. {0}", [
								`<a href="${message.checkout_url}" target="_blank">${__(
									"Click here to pay"
								)}</a>`,
							]),
							indicator: "orange",
						});
					}
				},
			});
		});

		frm.add_custom_button(__("Paymob Attempts"), () => {
			frappe.set_route("List", "Paymob Payment Attempt", { payment_request: frm.doc.name });
		});
	},
});
