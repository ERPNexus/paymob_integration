frappe.ui.form.on("Payment Request", {
	refresh(frm) {
		// ERPNext's own payment_request.js adds this button; it emails a payment link,
		// which doesn't fit our Paymob checkout flow.
		frm.remove_custom_button(__("Resend Payment Email"));

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
				state: ["in", ["Paid", "Partially Refunded"]],
			},
			fields: ["name", "state", "expected_amount_cents", "refunded_amount_cents"],
			order_by: "creation desc",
			limit: 1,
		})
		.then((attempts) => {
			const attempt = attempts[0];
			if (!attempt) return;
			// v15 has no custom "refund" right: the server requires the Paymob Refund Manager role.
			if (frappe.user.has_role("Paymob Refund Manager")) add_refund_buttons(frm, attempt);
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
