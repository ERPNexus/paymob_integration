"""What the payer pages show about a request: who is paid, for which invoice, how much."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate

RTL = ("ar", "fa", "he", "ur")


def fill(context, request):
	source = frappe.get_doc(request.reference_doctype, request.reference_name)
	context.update(
		{
			"title": _("Pay {0}").format(request.reference_name),
			"company_name": frappe.get_cached_value("Company", request.company, "company_name") or request.company,
			"customer_name": request.party_name or source.get("customer_name") or request.party,
			"invoice": request.reference_name,
			"invoice_date": formatdate(source.get("posting_date")),
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
