"""There is no event-type field in the processed callback payload — the flags *are* the type.
Order matters: a refund callback also carries `success: true`, and a wallet/kiosk pending
callback also carries `success: true`, so the reversal and pending flags are read first.
"""


def classify_event(obj):
	if obj.get("is_refunded"):
		return "Refund"
	if obj.get("is_voided") or obj.get("is_capture") or obj.get("is_auth"):
		return "Unsupported"
	if obj.get("pending"):
		return "Pending"
	if obj.get("success"):
		return "Success"
	return "Decline"


def unsupported_subtype(obj):
	for flag, subtype in (("is_voided", "Void"), ("is_capture", "Capture"), ("is_auth", "Auth")):
		if obj.get(flag):
			return subtype
	return None
