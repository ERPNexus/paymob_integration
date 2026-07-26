"""There is no event-type field in the processed callback payload — the flags *are* the type.
Order matters: a refund callback also carries `success: true`, and a wallet/kiosk pending
callback also carries `success: true`, so the reversal and pending flags are read first.
"""


def classify_event(obj):
	if obj.get("is_voided"):
		return "Void"
	if obj.get("is_refunded"):
		return "Refund"
	if obj.get("is_capture"):
		return "Capture"
	if obj.get("is_auth"):
		return "Auth"
	if obj.get("pending"):
		return "Pending"
	if obj.get("success"):
		return "Success"
	return "Decline"
