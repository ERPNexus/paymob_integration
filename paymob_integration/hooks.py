app_name = "paymob_integration"
app_title = "Paymob Integration"
app_publisher = "Abdelrahman Elsayed"
app_description = "Seamless integration for paymob with ERPNext"
app_email = "notabdelrahmanelsayed@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

add_to_apps_screen = [
	{
		"name": "paymob_integration",
		"logo": "/assets/paymob_integration/images/paymob-mark.svg",
		"title": "Paymob Integration",
		"route": "/app/paymob-integration",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/paymob_integration/css/paymob_integration.css"
# app_include_js = "/assets/paymob_integration/js/paymob_integration.js"

# include js, css files in header of web template
# web_include_css = "/assets/paymob_integration/css/paymob_integration.css"
# web_include_js = "/assets/paymob_integration/js/paymob_integration.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "paymob_integration/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Payment Request": "public/js/payment_request.js"}
after_install = "paymob_integration.notifications.seed"
after_migrate = [
	"paymob_integration.notifications.seed",
	"paymob_integration.notifications.refresh_defaults",
]
doc_events = {"Payment Request": {"validate": "paymob_integration.payment_request.prepare_payment_email"}}
jinja = {"methods": ["paymob_integration.pay_link.build"]}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "paymob_integration/public/icons.svg"

# Fixtures
# --------

fixtures = [
	{"doctype": "Role", "filters": [["name", "in", ["Paymob Refund Manager"]]]},
	{
		"doctype": "Number Card",
		"filters": [
			[
				"name",
				"in",
				["Pending Attempts", "Needs Attention", "Unprocessed Transactions"],
			]
		],
	},
]

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "paymob_integration.utils.jinja_methods",
# 	"filters": "paymob_integration.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "paymob_integration.install.before_install"
# after_install = "paymob_integration.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "paymob_integration.uninstall.before_uninstall"
# after_uninstall = "paymob_integration.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "paymob_integration.utils.before_app_install"
# after_app_install = "paymob_integration.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "paymob_integration.utils.before_app_uninstall"
# after_app_uninstall = "paymob_integration.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "paymob_integration.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "paymob_integration.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		# Paymob's webhook retry behaviour is undocumented and assumed to be zero, so this is the
		# only thing that recovers a lost callback.
		"*/15 * * * *": ["paymob_integration.tasks.reconcile_pending_attempts"],
	}
}

# Testing
# -------

# before_tests = "paymob_integration.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "paymob_integration.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "paymob_integration.event.get_events"
# }
#
# Adds Paymob attempts to Payment Request's native Connections dashboard.
override_doctype_dashboards = {
	"Payment Request": "paymob_integration.dashboard.get_payment_request_dashboard"
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["paymob_integration.utils.before_request"]
# after_request = ["paymob_integration.utils.after_request"]

# Job Events
# ----------
# before_job = ["paymob_integration.utils.before_job"]
# after_job = ["paymob_integration.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"paymob_integration.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
