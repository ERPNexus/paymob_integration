"""Pay one Sales Invoice or Sales Order by link: the shared server half of every "pay by card or
wallet" button, and each company's own Paymob account.

Callers (a rep app, a merchant app, a portal) check that the user may act on the document first;
this module only knows documents, Payment Requests and companies. Nothing here marks anything paid:
that stays with the signed callback or the reconciliation inquiry (rules/payments.md rule 1).
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, now_datetime

from paymob_integration import pay_link, tasks
from paymob_integration.paymob import client, session, settings

OPEN_STATES = ("Initiated", "Requested", "Partially Paid", "Payment Ordered")
# ponytail: one inquiry per attempt every few seconds is plenty for a screen that polls.
INQUIRY_GAP_SECONDS = 5
DEFAULT_BASE_URL = "https://accept.paymob.com"


def enabled():
	return settings.is_enabled()


def enabled_for(company: str) -> bool:
	"""Whether `company` can take Paymob payments now: keys and a card or wallet integration."""
	if not company or not settings.is_enabled():
		return False
	country, currency = frappe.get_cached_value("Company", company, ["country", "default_currency"])
	try:
		credentials = settings.get_credential_set(country, currency, company=company)
		settings.resolve_integrations(country, currency, company, credentials.mode)
	except frappe.ValidationError:
		return False
	# The money lands in this account, so it must be the company's own. A row with no company
	# (single-company sites) still serves its own company, never another tenant's documents.
	return bool(credentials.payment_account) and (
		frappe.db.get_value("Account", credentials.payment_account, "company") == company
	)


def owed(doc) -> float:
	"""What is still unpaid on an invoice or an order."""
	if doc.doctype == "Sales Order":
		return flt(flt(doc.rounded_total or doc.grand_total, 2) - flt(doc.advance_paid), 2)
	return flt(doc.get("outstanding_amount"), 2)


def link_for(invoice: str) -> dict:
	"""The open Payment Request for the invoice's whole outstanding amount, created if missing."""
	si = frappe.get_doc("Sales Invoice", invoice)
	if si.docstatus != 1 or si.is_return:
		frappe.throw(_("This invoice has nothing left to pay."))
	return _link(si, owed(si))


def link_for_order(order: str) -> dict:
	"""An advance against a submitted Sales Order, for what is not yet paid on it."""
	so = frappe.get_doc("Sales Order", order)
	if so.docstatus != 1 or so.status in ("Closed", "Completed", "On Hold"):
		frappe.throw(_("This order can't be paid online."))
	return _link(so, owed(so))


def status_for(payment_request: str) -> dict:
	"""Where one payment stands, asking Paymob first when a checkout is waiting on it."""
	attempt = frappe.db.get_value(
		"Paymob Payment Attempt",
		{"payment_request": payment_request},
		["name", "state", "last_polled_at", "paymob_order_id"],
		as_dict=True,
		order_by="creation desc",
	)
	# Only once Paymob has issued the order: before that the checkout is still saving this attempt,
	# and touching it here makes that save fail (TimestampMismatchError, seen with a 3 s poll).
	if (
		attempt
		and attempt.state == "Pending"
		and attempt.paymob_order_id
		and _due_for_inquiry(attempt.last_polled_at)
	):
		try:
			tasks._reconcile(attempt.name)
			frappe.db.commit()
		except client.PaymobError:
			pass  # still Pending; the next poll asks again
	request = frappe.get_doc("Payment Request", payment_request)
	return _describe(request, frappe.get_doc(request.reference_doctype, request.reference_name))


def company_status(company: str) -> dict:
	"""What a company's own Paymob setup looks like. Never returns a secret, only whether it is set."""
	row = _own_row(company)
	ids = [r for r in settings.get_settings().integration_ids if r.get("company") == company and r.enabled]
	return {
		"configured": bool(row),
		"ready": enabled_for(company),
		"mode": row.mode if row else None,
		"public_key": row.public_key if row else None,
		"has_secret_key": bool(row and row.get_password("secret_key", raise_exception=False)),
		"has_api_key": bool(row and row.get_password("api_key", raise_exception=False)),
		"has_hmac_secret": bool(row and row.get_password("hmac_secret", raise_exception=False)),
		"card_integration_id": next((r.integration_id for r in ids if r.payment_method == "card"), None),
		"wallet_integration_id": next((r.integration_id for r in ids if r.payment_method == "wallet"), None),
		"payment_account": row.payment_account if row else None,
	}


def configure_company(
	company: str,
	mode: str,
	public_key: str,
	card_integration_id: str,
	secret_key: str | None = None,
	api_key: str | None = None,
	hmac_secret: str | None = None,
	wallet_integration_id: str | None = None,
) -> dict:
	"""Save `company`'s own Paymob account: one enabled row in `mode`. A secret left empty keeps
	the one already saved, so a form never has to show a secret back to fill itself."""
	if mode not in ("Test", "Live"):
		frappe.throw(_("Mode must be Test or Live."))
	country, currency = frappe.get_cached_value("Company", company, ["country", "default_currency"])
	config = frappe.get_doc("Paymob Settings")
	row = _own_row(company, config)
	if not row:
		row = config.append("credential_sets", {"company": company, "base_url": DEFAULT_BASE_URL})
	row.update(
		{
			"enabled": 1,
			"country": country,
			"currency": currency,
			"mode": mode,
			"public_key": (public_key or "").strip(),
			"payment_account": row.payment_account or _payment_account(company, currency),
		}
	)
	for field, value in (("secret_key", secret_key), ("api_key", api_key), ("hmac_secret", hmac_secret)):
		if value and value.strip():
			row.set(field, value.strip())
	# A company has one account; its old integration rows go with the save.
	config.integration_ids = [r for r in config.integration_ids if r.get("company") != company]
	for method, value in (("card", card_integration_id), ("wallet", wallet_integration_id)):
		if value and str(value).strip():
			config.append(
				"integration_ids",
				{
					"enabled": 1,
					"company": company,
					"country": country,
					"currency": currency,
					"mode": mode,
					"payment_method": method,
					"integration_id": str(value).strip(),
				},
			)
	config.enabled = 1
	config.flags.ignore_permissions = True
	config.save()
	missing = [f for f in ("secret_key", "api_key", "hmac_secret") if not row.get_password(f, raise_exception=False)]
	if missing:
		frappe.throw(_("Fill in the secret key, API key and HMAC secret."))
	return company_status(company)


def _own_row(company, config=None):
	config = config or settings.get_settings()
	return next((r for r in config.credential_sets if r.get("company") == company and r.enabled), None)


def _payment_account(company, currency):
	"""The company's own clearing account for card and wallet money, made on first setup."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"Paymob - {abbr}"
	if frappe.db.exists("Account", name):
		return name
	parent = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Bank", "is_group": 1}, "name"
	) or frappe.db.get_value("Account", {"company": company, "account_name": "Bank Accounts", "is_group": 1}, "name")
	if not parent:
		frappe.throw(_("{0} has no bank accounts group to hold the Paymob account.").format(company))
	account = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": "Paymob",
			"parent_account": parent,
			"company": company,
			"account_type": "Bank",
			"account_currency": currency,
		}
	)
	account.flags.ignore_permissions = True
	return account.insert().name


def _link(doc, outstanding) -> dict:
	# ERPNext's PaymentRequest.validate re-checks read on the invoice/order as the session user,
	# and a merchant or rep session has none. Callers check ownership first (module docstring).
	with session.as_administrator():
		return _link_as_admin(doc, outstanding)


def _link_as_admin(doc, outstanding) -> dict:
	"""A link must never ask for more than is still owed: a request at another amount (a cash
	collection landed since) is cancelled and replaced, unless someone may be paying it now."""
	if not enabled_for(doc.company):
		frappe.throw(_("Card and wallet payments are not set up for {0}.").format(doc.company))
	if outstanding <= 0:
		frappe.throw(_("This invoice has nothing left to pay."))

	for row in _open_requests(doc.doctype, doc.name):
		if flt(row.grand_total, 2) == outstanding or _has_live_payment(row.name):
			return _describe(frappe.get_doc("Payment Request", row.name), doc)
		cancelled = frappe.get_doc("Payment Request", row.name)
		cancelled.flags.ignore_permissions = True
		cancelled.cancel()

	request = frappe.get_doc(
		{
			"doctype": "Payment Request",
			"payment_request_type": "Inward",
			"transaction_date": frappe.utils.nowdate(),
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"party_type": "Customer",
			"party": doc.customer,
			"party_name": doc.customer_name,
			"company": doc.company,
			"currency": doc.currency,
			"grand_total": outstanding,
			"payment_channel": "Email",
			"mute_email": 1,
			"email_to": doc.get("contact_email") or "",
			"subject": _("Payment Request for {0}").format(doc.name),
			"message": _("Pay {0}").format(doc.name),
		}
	)
	request.flags.ignore_permissions = True
	request.insert()
	request.submit()
	return _describe(request, doc)


def _describe(request, doc) -> dict:
	attempt_state = frappe.db.get_value(
		"Paymob Payment Attempt",
		{"payment_request": request.name},
		"state",
		order_by="creation desc",
	)
	paid = request.status == "Paid" or attempt_state in ("Paid", "Partially Refunded", "Refunded")
	return {
		"payment_request": request.name,
		"reference_doctype": doc.doctype,
		"invoice": doc.name,  # the paid document's name (an invoice or an order)
		"customer": doc.customer,
		"customer_name": doc.customer_name,
		"company": doc.company,
		"amount": flt(request.grand_total, 2),
		"currency": request.currency,
		"url": pay_link.build(request.name),
		# Open (link not used yet), Pending (on the card page), Paid, Failed, Expired, Cancelled.
		"state": "Paid" if paid else ("Cancelled" if request.docstatus == 2 else (attempt_state or "Open")),
	}


def _open_requests(doctype, name):
	return frappe.get_all(
		"Payment Request",
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"docstatus": 1,
			"status": ["in", OPEN_STATES],
		},
		fields=["name", "grand_total"],
		order_by="creation desc",
	)


def _has_live_payment(payment_request):
	return frappe.db.exists(
		"Paymob Payment Attempt",
		{"payment_request": payment_request, "state": ["in", ("Pending", "Paid")], "expires_at": [">", now_datetime()]},
	)


def _due_for_inquiry(last_polled_at):
	return not last_polled_at or last_polled_at < add_to_date(now_datetime(), seconds=-INQUIRY_GAP_SECONDS)


def refuse_cancel_while_paid(doc, method=None):
	"""Owner rule: an order paid by card or wallet is refunded first, then cancelled. Keeping the
	money as the shop's credit instead is a deliberate call: set doc.flags.paymob_keep_as_credit.
	Not a role check: apps cancel orders elevated, and Administrator holds every role."""
	if doc.flags.paymob_keep_as_credit:
		return
	requests = frappe.get_all(
		"Payment Request", filters={"reference_doctype": doc.doctype, "reference_name": doc.name}, pluck="name"
	)
	if requests and frappe.db.exists(
		"Paymob Payment Attempt", {"payment_request": ["in", requests], "state": ["in", ("Paid", "Partially Refunded")]}
	):
		frappe.throw(
			_("This order was paid by card or wallet. Refund the payment first, then cancel the order."),
			title=_("Refund first"),
		)
