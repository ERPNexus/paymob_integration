"""The only module that talks to the network. Every Paymob call goes through request()."""

import frappe
import requests
from frappe import _

DEFAULT_TIMEOUT = 30


class PaymobError(frappe.ValidationError):
	"""Base class for every Paymob failure."""


class PaymobNetworkError(PaymobError):
	"""We never reached Paymob, or never heard back. Says nothing about the money."""


class PaymobAPIError(PaymobError):
	"""Paymob answered with a non-2xx status."""

	def __init__(self, message, status_code=None):
		super().__init__(message)
		self.status_code = status_code


def request(method, url, *, headers=None, json_body=None, timeout=DEFAULT_TIMEOUT):
	"""Call Paymob and return the decoded JSON body without exposing response content on errors."""
	try:
		response = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
	except requests.Timeout as exc:
		raise PaymobNetworkError(
			_("Paymob did not answer in time. The payment has not changed. Please try again.")
		) from exc
	except requests.RequestException as exc:
		raise PaymobNetworkError(
			_("Could not reach Paymob. The payment has not changed. Please try again.")
		) from exc

	if response.status_code >= 400:
		raise PaymobAPIError(
			_("Paymob rejected the request. Check the credentials and try again."),
			status_code=response.status_code,
		)

	try:
		return response.json()
	except requests.JSONDecodeError as exc:
		raise PaymobAPIError(
			_("Paymob returned an invalid response. Please try again."), status_code=response.status_code
		) from exc
