"""What the payer pages show about a request: who is paid, for which invoice, how much."""

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate

RTL = ("ar", "fa", "he", "ur")
AR_DAYS = ("الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
AR_MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")


def doc_number(name: str | None) -> str | None:
	"""The short number a payer can read, the same rule as the Modar apps' docNumber: the serial after
	the 4-digit year, leading zeros stripped, amendment suffix ignored (ACC-SINV-2026-04258-1 -> 4258);
	else the trailing digits; None when there are none, so the page shows nothing rather than the raw id."""
	v = (name or "").strip()
	m = re.search(r"-(\d{4})-(\d+)(-\d+)?$", v)
	serial = m.group(2) if m else (re.search(r"(\d+)\D*$", v) or [None, None])[1]
	if serial is None:
		return None
	return serial.lstrip("0") or "0"


def friendly_date(value) -> str:
	"""«الأحد 22 نوفمبر» (Arabic) or «Sun 22 Nov» (other languages); the year only when it isn't this one."""
	if not value:
		return ""
	d = getdate(value)
	year = "" if d.year == getdate().year else f" {d.year}"
	if (frappe.local.lang or "en").split("-")[0] == "ar":
		return f"{AR_DAYS[d.weekday()]} {d.day} {AR_MONTHS[d.month - 1]}{year}"
	return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}{year}"


def fill(context, request):
	source = frappe.get_doc(request.reference_doctype, request.reference_name)
	number = doc_number(request.reference_name)
	context.update(
		{
			"title": _("Pay {0}").format(number or request.reference_name),
			"company_name": frappe.get_cached_value("Company", request.company, "company_name") or request.company,
			"customer_name": request.party_name or source.get("customer_name") or request.party,
			"invoice": number,
			"doc_label": _("Order") if request.reference_doctype == "Sales Order" else _("Invoice"),
			"invoice_date": friendly_date(source.get("posting_date") or source.get("transaction_date")),
			"amount": "{:,.2f}".format(flt(request.grand_total, 2)),
			"currency_label": _("EGP") if request.currency == "EGP" else request.currency,
		}
	)
	return context


def error(context, message):
	context.state = "Error"
	context.message = message
	context.setdefault("company_name", "")
	return context


def lang_attrs():
	lang = (frappe.local.lang or "en").split("-")[0]
	return {"lang": lang, "dir": "rtl" if lang in RTL else "ltr"}
