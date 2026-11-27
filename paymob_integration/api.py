"""Whitelisted entry points for logged-in Desk users."""

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_default_address
from frappe.utils import add_to_date, get_url, now_datetime, validate_email_address, validate_phone_number
from frappe.utils.synchronization import filelock

from paymob_integration.paymob import amounts, audit, intention, refund, settings, transactions

WEBHOOK_PATH = "/api/method/paymob_integration.webhooks.processed_callback"
RESULT_PATH = "/paymob-result"
TEST_PHONE_NUMBER = "+201000000000"
REFUND_ROLE = "Paymob Refund Manager"
REFUND_CONFIRMATION_MINUTES = 20


@frappe.whitelist(methods=["POST"])
def request_refund(attempt: str, amount_cents: int):
	"""Request one refund under a row lock; its signed callback remains ledger authority."""
	attempt_doc = frappe.get_doc("Paymob Payment Attempt", attempt, for_update=True)
	# v15 has no custom permission types, so the v16 "refund" right becomes a role check.
	attempt_doc.check_permission("read")
	if REFUND_ROLE not in frappe.get_roles():
		raise frappe.PermissionError(_("Only a Paymob Refund Manager can refund Paymob payments."))
	settings.is_enabled(throw=True)
	window_start = add_to_date(now_datetime(), minutes=-REFUND_CONFIRMATION_MINUTES)
	if attempt_doc.refund_requested_at and attempt_doc.refund_requested_at >= window_start:
		frappe.throw(_("A previous refund is awaiting Paymob confirmation."))
	if attempt_doc.state not in ("Paid", "Partially Refunded"):
		frappe.throw(_("Only paid Paymob payments can be refunded."))

	try:
		amount_cents = int(amount_cents)
	except (TypeError, ValueError):
		frappe.throw(_("The refund amount must be greater than zero."))
	if amount_cents <= 0:
		frappe.throw(_("The refund amount must be greater than zero."))

	charged = _verified_charge(attempt_doc)
	remaining = charged.amount_cents - (attempt_doc.refunded_amount_cents or 0)
	if amount_cents > remaining:
		frappe.throw(_("The refund amount cannot exceed the remaining paid amount."))

	attempt_doc.db_set("refund_requested_at", now_datetime())
	audit.record(
		None,
		attempt_doc,
		event="Refund Requested",
		needs_action=0,
		description=_("A refund of {0} {1} was requested.").format(attempt_doc.currency, amount_cents),
		actor=frappe.session.user,
		received_amount_cents=amount_cents,
		received_currency=attempt_doc.currency,
	)
	credentials = settings.get_credential_set(
		attempt_doc.country, attempt_doc.currency, attempt_doc.mode, settings.attempt_company(attempt_doc)
	)
	refund.request(credentials, transaction_id=charged.paymob_transaction_id, amount_cents=amount_cents)
	return {"status": "requested"}


def _verified_charge(attempt):
	charged = transactions.verified_charge(attempt.name)
	if not charged:
		frappe.throw(_("No verified Paymob charge is available to reverse."))
	if charged.currency != attempt.currency:
		frappe.throw(_("The verified Paymob charge currency does not match this attempt."))
	return charged


@frappe.whitelist(methods=["GET"])
def get_enabled_status():
	return {"enabled": settings.is_enabled()}


@frappe.whitelist(methods=["POST"])
def start_checkout(payment_request: str):
	"""Create a checkout from the stored Payment Request, never browser-supplied money.

	Reuses a still-pending, unexpired attempt so repeat clicks on the Desk Pay button and the
	emailed payer link (paymob_pay.py) never mint two Paymob orders for one Payment Request.
	"""
	request = frappe.get_doc("Payment Request", payment_request)
	request.check_permission("write")
	return _checkout(request, reuse_pending=True)


def _checkout(request, reuse_pending=False):
	"""Create, or safely reuse, the hosted checkout for a submitted request."""
	if reuse_pending:
		# Payer links can be opened in multiple browser tabs at once. Keep the lookup, intention
		# creation, and identifier save together so only one live checkout is created per request.
		with filelock(f"paymob-checkout-{request.name}"):
			request = frappe.get_doc("Payment Request", request.name)
			return _checkout_for_request(request, reuse_pending=True)
	return _checkout_for_request(request)


def _checkout_for_request(request, reuse_pending=False):
	"""Run one checkout flow; payer-link callers hold their request-scoped lock."""
	_validate_payable(request)
	source = frappe.get_doc(request.reference_doctype, request.reference_name)
	country = _merchant_country(request, source)
	credentials = settings.get_credential_set(country, request.currency, company=request.company)
	integration_ids = settings.resolve_integrations(country, request.currency, request.company, credentials.mode)
	if reuse_pending:
		attempt = _active_attempt(request.name)
		if attempt:
			client_secret = attempt.get_password("client_secret")
			if client_secret:
				credentials = settings.get_credential_set(attempt.country, attempt.currency, attempt.mode, request.company)
				return {
					"attempt": attempt.name,
					"checkout_url": build_checkout_url(credentials, client_secret),
				}

	billing_data = _billing_data(request, source)
	attempt = _create_attempt(request, credentials, _contact_email(request, source))
	result = intention.create_intention(
		credentials,
		amount_cents=attempt.expected_amount_cents,
		currency=attempt.currency,
		special_reference=attempt.special_reference,
		billing_data=billing_data,
		items=_items(request, attempt.expected_amount_cents),
		notification_url=get_url(WEBHOOK_PATH),
		redirection_url=get_url(RESULT_PATH),
		expiration=settings.get_settings().intention_expiration_seconds,
		integration_ids=integration_ids,
	)
	attempt.update(
		{
			"paymob_intention_id": result["intention_id"],
			"paymob_order_id": result["order_id"],
		}
	)
	attempt.set("client_secret", result["client_secret"])
	attempt.save(ignore_permissions=True)
	frappe.db.commit()

	frappe.logger("paymob").info(
		f"intention created payment_request={request.name} "
		f"order_id={result['order_id']} expected_cents={attempt.expected_amount_cents} "
	)
	return {
		"attempt": attempt.name,
		"checkout_url": build_checkout_url(credentials, result["client_secret"]),
	}


def _active_attempt(payment_request):
	"""Return a ready, unexpired checkout so a browser refresh or a retry after a failed
	transaction reuses the same Paymob intention instead of minting a new order ID.

	Paymob does not consume the intention on a failed transaction, only on success, so a
	Failed attempt within its original expiry window is still safe to reopen.
	"""
	name = frappe.db.get_value(
		"Paymob Payment Attempt",
		{
			"payment_request": payment_request,
			"state": ["in", ("Pending", "Failed")],
			"expires_at": [">", now_datetime()],
			"paymob_intention_id": ["is", "set"],
			"paymob_order_id": ["is", "set"],
		},
		"name",
		order_by="expires_at desc",
	)
	return name and frappe.get_doc("Paymob Payment Attempt", name)


def build_checkout_url(credentials, client_secret):
	"""Only browser-safe public and per-session keys reach the hosted checkout URL."""
	query = urlencode({"publicKey": credentials.public_key, "clientSecret": client_secret})
	return f"{settings.base_url(credentials)}/unifiedcheckout/?{query}"


def _validate_payable(request):
	if request.docstatus != 1:
		frappe.throw(_("Submit the Payment Request before starting a payment."))
	if request.payment_request_type != "Inward":
		frappe.throw(_("Paymob checkout is only available for incoming Payment Requests."))
	if request.status in ("Paid", "Cancelled"):
		frappe.throw(_("This Payment Request is already {0}.").format(_(request.status)))
	if amounts.to_minor_units(request.grand_total, request.currency) <= 0:
		frappe.throw(_("The Payment Request amount must be greater than zero."))
	if not request.get("reference_doctype") or not request.get("reference_name"):
		frappe.throw(_("The Payment Request needs a reference document before starting Paymob checkout."))


def _merchant_country(request, source):
	"""Resolve the Paymob account region from the merchant company."""
	company = request.get("company")
	if not company:
		company = source.get("company")
	if not company:
		frappe.throw(_("The Payment Request needs a company before starting Paymob checkout."))
	country = frappe.get_cached_value("Company", company, "country")
	if not country:
		frappe.throw(_("Company {0} needs a country before starting Paymob checkout.").format(company))
	return country


def _create_attempt(request, credentials, contact_email=None):
	"""Persist the reference before Paymob is called, so failures cannot reuse it."""
	sequence = frappe.db.count("Paymob Payment Attempt", {"payment_request": request.name}) + 1
	config = settings.get_settings()
	attempt = frappe.get_doc(
		{
			"doctype": "Paymob Payment Attempt",
			"special_reference": f"{request.name}-{sequence}",
			"payment_request": request.name,
			"state": "Pending",
			"expected_amount_cents": amounts.to_minor_units(request.grand_total, request.currency),
			"currency": request.currency,
			"country": credentials.country,
			"mode": credentials.mode,
			"contact_email": contact_email,
			"expires_at": add_to_date(now_datetime(), seconds=config.intention_expiration_seconds),
		}
	)
	attempt.insert(ignore_permissions=True)
	frappe.db.commit()
	return attempt


def _billing_data(request, source):
	"""Paymob requires these keys; customer data stays on existing ERPNext records."""
	phone_number = source.get("contact_mobile") or request.get("phone_number")
	if not phone_number and settings.get_settings().mode == "Test":
		phone_number = TEST_PHONE_NUMBER
	if not validate_phone_number(phone_number):
		frappe.throw(
			_("The Payment Request needs a valid customer phone number before starting Paymob checkout.")
		)
	contact = (
		frappe.db.get_value(
			"Contact", source.get("contact_person"), ["first_name", "last_name"], as_dict=True
		)
		or {}
	)
	return {
		"first_name": contact.get("first_name") or request.party or "NA",
		"last_name": contact.get("last_name") or "NA",
		# Unlike the other "NA" placeholders below, Paymob format-validates this field and
		# rejects both "NA" and non-email values such as a fallback user ID.
		"email": _contact_email(request, source) or "na@na.com",
		"phone_number": phone_number,
		"street": "NA",
		"building": "NA",
		"floor": "NA",
		"apartment": "NA",
		"city": "NA",
		"state": "NA",
		"country": _billing_country(request, source),
	}


def _contact_email(request, source):
	return validate_email_address(source.get("contact_email")) or validate_email_address(request.email_to)


def _billing_country(request, source):
	address = source.get("customer_address")
	country = address and frappe.db.get_value("Address", address, "country")
	if country:
		code = frappe.db.get_value("Country", country, "code")
		return code.upper() if code else "NA"

	address = get_default_address(request.party_type, request.party)
	if not address:
		return "NA"
	country = frappe.db.get_value("Address", address, "country")
	code = country and frappe.db.get_value("Country", country, "code")
	return code.upper() if code else "NA"


def _items(request, amount_cents):
	return [
		{
			"name": request.reference_name,
			"amount": int(amount_cents),
			"description": request.subject or request.reference_name,
			"quantity": 1,
		}
	]
