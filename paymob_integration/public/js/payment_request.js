frappe.ui.form.on("Payment Request", {
	refresh(frm) {
		if (
			frm.doc.docstatus !== 1 ||
			frm.doc.payment_request_type !== "Inward" ||
			frm.doc.status === "Cancelled"
		)
			return;

		frappe
			.call({ method: "paymob_integration.api.get_enabled_status", type: "GET" })
			.then(({ message }) => {
				if (!message?.enabled) return;
				if (frm.doc.status !== "Paid") add_checkout_button(frm);
				add_action_buttons(frm);
			});
	},
});

function add_action_buttons(frm) {
	frappe.db
		.get_list("Paymob Payment Attempt", {
			filters: {
				payment_request: frm.doc.name,
				state: ["in", ["Authorized", "Paid", "Partially Refunded"]],
			},
			fields: ["name", "state", "expected_amount_cents", "refunded_amount_cents"],
			order_by: "creation desc",
			limit: 1,
		})
		.then((attempts) => {
			const attempt = attempts[0];
			if (!attempt) return;
			// "refund" is a custom Permission Type; frappe.perm.has_perm only knows the
			// built-in rights, so the check has to go through the server.
			frappe
				.call({
					method: "frappe.client.has_permission",
					args: {
						doctype: "Paymob Payment Attempt",
						docname: attempt.name,
						perm_type: "refund",
					},
				})
				.then(({ message }) => {
					if (message?.has_permission) add_refund_buttons(frm, attempt);
				});
		});
}

function add_checkout_button(frm) {
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
}

function add_refund_buttons(frm, attempt) {
	if (attempt.state === "Authorized") {
		frm.add_custom_button(__("Capture"), () => {
			frappe.call({
				method: "paymob_integration.api.request_capture",
				args: { attempt: attempt.name },
				freeze: true,
				freeze_message: __("Requesting Paymob capture..."),
			});
		});
		frm.add_custom_button(__("Void"), () => {
			frappe.call({
				method: "paymob_integration.api.request_void",
				args: { attempt: attempt.name },
				freeze: true,
				freeze_message: __("Requesting Paymob void..."),
			});
		});
		return;
	}
	const remaining = attempt.expected_amount_cents - (attempt.refunded_amount_cents || 0);
	frm.add_custom_button(__("Refund"), () => {
		frappe.prompt(
			{
				fieldname: "amount_cents",
				fieldtype: "Int",
				label: __("Refund Amount Cents"),
				default: remaining,
				reqd: 1,
			},
			({ amount_cents }) =>
				frappe.call({
					method: "paymob_integration.api.request_refund",
					args: { attempt: attempt.name, amount_cents },
					freeze: true,
					freeze_message: __("Requesting Paymob refund..."),
				}),
			__("Refund")
		);
	});
}
