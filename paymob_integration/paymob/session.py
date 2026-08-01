"""Run privileged work inside a request without corrupting the caller's session (issue #8;
rules/frappe-discipline.md — never call bare `frappe.set_user` on a path reachable from a
request).

`frappe.set_user` is safe in an enqueued RQ job, which has no live session to protect. Called
inside an HTTP/web request, its `local.session.sid = username` and `local.session.data = _dict()`
lines overwrite the real session id and discard csrf_token/session_expiry/user_agent/etc — and
restoring the original user with a second bare `set_user` call does the same damage again, because
`set_user` always stamps `sid` to the *username* it's given, never the real sid. `as_administrator`
saves the three things `set_user` clobbers (`session.sid`, `session.data`, `local.form_dict`) and
puts them back after switching back, so the caller's session survives the round trip.
"""

from contextlib import contextmanager

import frappe


@contextmanager
def as_administrator():
	"""No-op when the caller is already Administrator. Otherwise run the wrapped block as
	Administrator, then restore the caller's session id, session data and form dict — the three
	things `frappe.set_user` overwrites on the way out and never restores.
	"""
	if frappe.session.user == "Administrator":
		yield
		return

	original_user = frappe.session.user
	saved_sid = frappe.local.session.sid
	saved_session_data = frappe.local.session.data
	saved_form_dict = frappe.local.form_dict
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		# Reset local.cache, role_permissions, user_perms and jenv_* for original_user correctly —
		# then put back what this second set_user call clobbers again (sid, session.data, form_dict).
		frappe.set_user(original_user)
		frappe.local.session.sid = saved_sid
		frappe.local.session.data = saved_session_data
		frappe.local.form_dict = saved_form_dict
