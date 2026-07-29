"""Small, inline-styled email card shared by Paymob notifications."""


def render(title, status, tone, body, company, cta_label=None, cta_url=None, details=""):
	"""Return a mobile-safe Jinja email fragment without remote assets."""
	cta = ""
	if cta_label and cta_url:
		cta = f"""
							<tr>
								<td align="{{{{ 'right' if is_rtl() else 'left' }}}}" style="padding: 0 32px 24px;">
									<a href="{cta_url}" style="background: #0180fd; border-radius: 6px; color: #ffffff; display: inline-block; font-family: Arial, sans-serif; font-size: 16px; font-weight: 700; line-height: 20px; padding: 12px 20px; text-decoration: none;">{cta_label}</a>
								</td>
							</tr>"""

	return f"""<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background: #f3f6f9; border-collapse: collapse; width: 100%;">
	<tr>
		<td align="center" style="padding: 24px 12px;">
			<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" style="background: #ffffff; border-collapse: collapse; max-width: 600px; width: 100%;">
				<tr>
					<td dir="{{{{ 'rtl' if is_rtl() else 'ltr' }}}}" align="{{{{ 'right' if is_rtl() else 'left' }}}}" style="background: #0180fd; color: #ffffff; font-family: Arial, sans-serif; font-size: 20px; font-weight: 700; line-height: 26px; padding: 24px 32px;">
						{{{{ {company} }}}}
					</td>
				</tr>
				<tr>
					<td dir="{{{{ 'rtl' if is_rtl() else 'ltr' }}}}" align="{{{{ 'right' if is_rtl() else 'left' }}}}" style="color: #1f2937; font-family: Arial, sans-serif; padding: 28px 32px 8px;">
						<span style="background: {tone["background"]}; border-radius: 999px; color: {tone["text"]}; display: inline-block; font-size: 14px; font-weight: 700; line-height: 18px; padding: 5px 10px;">{status}</span>
						<h1 style="color: #111827; font-size: 24px; line-height: 30px; margin: 16px 0 12px;">{title}</h1>
						<div style="color: #374151; font-size: 16px; line-height: 24px;">{body}</div>
						{details}
					</td>
				</tr>{cta}
				<tr>
					<td dir="{{{{ 'rtl' if is_rtl() else 'ltr' }}}}" align="{{{{ 'right' if is_rtl() else 'left' }}}}" style="border-top: 1px solid #e5e7eb; color: #6b7280; font-family: Arial, sans-serif; font-size: 13px; line-height: 18px; padding: 16px 32px;">
						{{{{ _('This is an automated message from {{0}}.').format({company}) }}}}
					</td>
				</tr>
			</table>
		</td>
	</tr>
</table>"""


INFO = {"background": "#e0f2fe", "text": "#075985"}
SUCCESS = {"background": "#dcfce7", "text": "#166534"}
WARNING = {"background": "#fef3c7", "text": "#92400e"}
ERROR = {"background": "#fee2e2", "text": "#b91c1c"}
NEUTRAL = {"background": "#f3f4f6", "text": "#374151"}
