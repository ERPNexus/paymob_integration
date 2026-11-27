"""Direct unit test of `as_administrator()` (fix for issue #8): everything `frappe.set_user`
clobbers on its way out of a privileged block — session id, session data, form dict — must come
back exactly as it was, even when the wrapped block raises.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from paymob_integration.paymob import session


class TestAsAdministrator(FrappeTestCase):
	def setUp(self):
		self.original_user = frappe.session.user
		self.addCleanup(frappe.set_user, self.original_user)

	def _stamp_non_admin_session(self):
		frappe.set_user("customer@example.test")
		sid = "sentinel-sid-1234"
		data = frappe._dict({"csrf_token": "sentinel-token", "session_expiry": "2099-01-01"})
		form_dict = frappe._dict({"cmd": "sentinel.method"})
		frappe.local.session.sid = sid
		frappe.local.session.data = data
		frappe.local.form_dict = form_dict
		return sid, data, form_dict

	def test_runs_the_block_as_administrator_and_restores_the_session_after(self):
		sid, data, form_dict = self._stamp_non_admin_session()

		with session.as_administrator():
			self.assertEqual(frappe.session.user, "Administrator")

		self.assertEqual(frappe.session.user, "customer@example.test")
		self.assertEqual(frappe.local.session.sid, sid)
		self.assertIs(frappe.local.session.data, data)
		self.assertIs(frappe.local.form_dict, form_dict)

	def test_already_administrator_is_a_no_op(self):
		frappe.set_user("Administrator")
		sid = frappe.local.session.sid
		data = frappe.local.session.data
		form_dict = frappe.local.form_dict

		with session.as_administrator():
			self.assertEqual(frappe.session.user, "Administrator")

		self.assertEqual(frappe.session.user, "Administrator")
		self.assertIs(frappe.local.session.sid, sid)
		self.assertIs(frappe.local.session.data, data)
		self.assertIs(frappe.local.form_dict, form_dict)

	def test_session_is_restored_even_when_the_block_raises(self):
		sid, data, form_dict = self._stamp_non_admin_session()

		with self.assertRaises(ValueError):
			with session.as_administrator():
				raise ValueError("boom")

		self.assertEqual(frappe.session.user, "customer@example.test")
		self.assertEqual(frappe.local.session.sid, sid)
		self.assertIs(frappe.local.session.data, data)
		self.assertIs(frappe.local.form_dict, form_dict)
