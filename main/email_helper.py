"""
Email helper — sends automated order emails via the Gmail API.
Uses the same OAuth token as the Google Workspace skill.
"""
import os
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    GOOGLE_AVAILABLE = True
except ImportError:
    Credentials = None
    build = None
    Request = None
    GOOGLE_AVAILABLE = False

# Path to the shared Google token (same one the Google Workspace skill uses)
TOKEN_PATH = os.path.expanduser('~/.hermes/google_token.json')


def send_order_email(order):
    """Send a thank-you + upload link email after a successful purchase."""
    user_email = order.user.email
    user_name = order.user.get_full_name() or order.user.username
    deceased = order.deceased_name or 'your loved one'

    # Build the email
    msg = MIMEMultipart('alternative')
    msg['To'] = user_email
    msg['From'] = 'mmsantelopevalley@gmail.com'
    msg['Subject'] = f'Thank you for your order #{order.id} — Memorial Media Services'

    upload_url = f'{os.environ.get("SITE_URL", "http://localhost:8000")}/upload/'

    text_body = f"""Hi {user_name},

Thank you for choosing Memorial Media Services for {deceased}'s tribute.

WHAT HAPPENS NEXT:

1. UPLOAD YOUR PHOTOS
   Visit the link below to upload your photos:
   {upload_url}

   We accept JPG, PNG, GIF, and WebP files. For best results, choose high-resolution images.

2. WE CRAFT YOUR TRIBUTE
   Our designers create a beautiful HD slideshow with music. You'll receive a preview link within 24-48 hours. Need it faster? Let us know.

3. REVIEW & APPROVE
   We offer unlimited revisions — if anything isn't right, just tell us and we'll fix it.

4. RECEIVE YOUR FILES
   Your finished HD video (and memorial flyer if you ordered the full package) will be available for download from your dashboard and sent to this email.

QUESTIONS?
Reply to this email or call us anytime.

With care,
The Memorial Media Services Team
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f0eb;margin:0;padding:0;">
<table cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
<tr><td style="background:linear-gradient(135deg,#1a2a3a,#2c3e50);padding:40px 30px;text-align:center;">
<h1 style="color:#c9a84c;margin:0 0 8px;font-size:28px;">Thank You for Your Order!</h1>
<p style="color:#fff;margin:0;font-size:15px;">Order #{order.id} &mdash; {order.get_tier_display()}</p>
</td></tr>
<tr><td style="padding:30px;">
<p style="font-size:16px;color:#333;line-height:1.6;">Hi <strong>{user_name}</strong>,</p>
<p style="font-size:16px;color:#333;line-height:1.6;">Thank you for choosing Memorial Media Services for <strong>{deceased}</strong>'s tribute. We're honored to help you create something beautiful.</p>

<div style="background:#f9f6f2;border-left:4px solid #c9a84c;padding:20px;margin:24px 0;border-radius:0 8px 8px 0;">
<h3 style="color:#1a2a3a;margin:0 0 12px;font-size:16px;">How It Works</h3>

<div style="display:flex;align-items:flex-start;margin-bottom:16px;">
<div style="background:#c9a84c;color:#fff;border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;font-size:13px;font-weight:bold;margin-right:12px;flex-shrink:0;">1</div>
<div><strong style="color:#1a2a3a;">Upload Your Photos</strong><br>
<a href="{upload_url}" style="color:#c9a84c;">Click here to upload</a> &mdash; JPG, PNG, GIF, or WebP. Hi-res is best.</div>
</div>

<div style="display:flex;align-items:flex-start;margin-bottom:16px;">
<div style="background:#c9a84c;color:#fff;border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;font-size:13px;font-weight:bold;margin-right:12px;flex-shrink:0;">2</div>
<div><strong style="color:#1a2a3a;">We Craft Your Tribute</strong><br>
Our designers create a cinematic HD slideshow with licensed music. You'll receive a preview within 24-48 hours.</div>
</div>

<div style="display:flex;align-items:flex-start;margin-bottom:16px;">
<div style="background:#c9a84c;color:#fff;border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;font-size:13px;font-weight:bold;margin-right:12px;flex-shrink:0;">3</div>
<div><strong style="color:#1a2a3a;">Review &amp; Approve</strong><br>
Unlimited revisions. If anything isn't right, just tell us and we'll fix it.</div>
</div>

<div style="display:flex;align-items:flex-start;">
<div style="background:#c9a84c;color:#fff;border-radius:50%;width:24px;height:24px;text-align:center;line-height:24px;font-size:13px;font-weight:bold;margin-right:12px;flex-shrink:0;">4</div>
<div><strong style="color:#1a2a3a;">Receive Your Files</strong><br>
Your finished HD video and flyer (if ordered) will be available for download from <a href="{os.environ.get('SITE_URL', 'http://localhost:8000')}/dashboard/" style="color:#c9a84c;">your dashboard</a>.</div>
</div>
</div>

<p style="font-size:16px;color:#333;line-height:1.6;">Have questions? Just reply to this email. We'll get back to you within 2 hours.</p>
</td></tr>
<tr><td style="background:#f5f0eb;padding:20px 30px;text-align:center;font-size:13px;color:#888;">
Memorial Media Services &bull; California City, CA<br>
<a href="mailto:mmsantelopevalley@gmail.com" style="color:#c9a84c;text-decoration:none;">mmsantelopevalley@gmail.com</a>
</td></tr>
</table>
</body>
</html>"""

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    # Channel 1: Gmail API
    ok1, err1 = _send_via_gmail(msg)
    if ok1:
        _log_alert('email_gmail', order.id, 'sent')
        return True, 'Sent via Gmail API'

    # Channel 2: SMTP fallback (if configured)
    ok2, err2 = _send_via_smtp(msg)
    if ok2:
        _log_alert('email_smtp', order.id, 'sent (Gmail API failed: %s)' % err1)
        return True, 'Sent via SMTP fallback'

    # Both failed — durable log record so the alert is never lost silently
    _log_alert('email_gmail', order.id, 'FAILED: %s' % err1)
    _log_alert('email_smtp', order.id, 'FAILED: %s' % err2)
    return False, f'Both channels failed. Gmail: {err1} | SMTP: {err2}'


def _send_via_smtp(msg):
    """Fallback channel — Django SMTP backend (uses settings.EMAIL_*)."""
    try:
        from django.conf import settings
        from django.core.mail import EmailMessage

        if not settings.EMAIL_HOST_USER:
            return False, 'SMTP not configured (EMAIL_HOST_USER empty)'

        email = EmailMessage(
            subject=msg['Subject'],
            body=msg.as_string(),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[msg['To']],
        )
        email.content_subtype = 'html'
        email.send(fail_silently=False)
        return True, 'Sent via SMTP'
    except Exception as e:
        return False, str(e)


def _log_alert(channel, order_id, status):
    """Append a durable line to the order alert log — never loses an alert."""
    try:
        from django.conf import settings
        from datetime import datetime
        path = getattr(settings, 'ORDER_ALERT_LOG', 'order_alerts.log')
        with open(path, 'a') as f:
            f.write(f'[{datetime.now().isoformat()}] order#{order_id} {channel}: {status}\n')
    except Exception:
        pass  # Logging must never break the request


def send_completion_email(slideshow):
    """Notify customer that their finished tribute is ready to download."""
    user_email = slideshow.user.email
    user_name = slideshow.user.get_full_name() or slideshow.user.username
    order = slideshow.order
    site_url = os.environ.get('SITE_URL', 'http://localhost:8000')

    msg = MIMEMultipart('alternative')
    msg['To'] = user_email
    msg['From'] = 'mmsantelopevalley@gmail.com'
    msg['Subject'] = f'Your tribute is ready! Order #{order.id} — Memorial Media Services'

    dashboard_url = f'{site_url}/dashboard/'

    text_body = f"""Hi {user_name},

Great news! Your tribute is complete and ready to download.

Your finished files:
- HD Tribute Video
- Memorial Flyer PDF (if ordered)

Visit your dashboard to download:
{dashboard_url}

If you have any questions or need changes, just reply to this email — we offer unlimited revisions.

Thank you for trusting us with your tribute.

With care,
The Memorial Media Services Team
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f0eb;margin:0;padding:0;">
<table cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
<tr><td style="background:linear-gradient(135deg,#1a2a3a,#2c3e50);padding:40px 30px;text-align:center;">
<h1 style="color:#c9a84c;margin:0 0 8px;font-size:28px;">Your Tribute Is Ready! 🎉</h1>
<p style="color:#fff;margin:0;font-size:15px;">Order #{order.id} &mdash; {order.get_tier_display()}</p>
</td></tr>
<tr><td style="padding:30px;">
<p style="font-size:16px;color:#333;line-height:1.6;">Hi <strong>{user_name}</strong>,</p>
<p style="font-size:16px;color:#333;line-height:1.6;">Your tribute is complete and ready for download. We've put care into every detail and hope it brings comfort to you and your family.</p>

<div style="background:#f9f6f2;border-left:4px solid #c9a84c;padding:20px;margin:24px 0;border-radius:0 8px 8px 0;">
<h3 style="color:#1a2a3a;margin:0 0 12px;">Your Files</h3>
<p style="margin:0 0 8px;">📹 HD Tribute Video</p>
<p style="margin:0;">📄 Memorial Flyer PDF (if ordered)</p>
</div>

<p style="text-align:center;margin:24px 0;">
<a href="{dashboard_url}" style="background:#c9a84c;color:#1a2a3a;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;">
    Download from Your Dashboard →
</a>
</p>

<p style="font-size:16px;color:#333;line-height:1.6;">If anything isn't perfect, just reply to this email. We offer unlimited revisions and want you to love the result.</p>
</td></tr>
<tr><td style="background:#f5f0eb;padding:20px 30px;text-align:center;font-size:13px;color:#888;">
Memorial Media Services &bull; California City, CA<br>
<a href="mailto:mmsantelopevalley@gmail.com" style="color:#c9a84c;text-decoration:none;">mmsantelopevalley@gmail.com</a>
</td></tr>
</table>
</body>
</html>"""

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    return _send_via_gmail(msg)


def _send_via_gmail(msg):
    """Low-level Gmail API send — shared by all email functions."""
    if not GOOGLE_AVAILABLE:
        return False, 'Google API packages not installed'
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_PATH)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            import json
            with open(TOKEN_PATH, 'w') as f:
                f.write(creds.to_json())

        service = build('gmail', 'v1', credentials=creds)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('ascii')
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        return True, 'Email sent'
    except Exception as e:
        return False, str(e)


def send_new_order_notification(order):
    """Notify the business owner that a new order was placed and paid."""
    owner_email = os.environ.get('OWNER_EMAIL', 'mmsantelopevalley@gmail.com')
    user_name = order.user.get_full_name() or order.user.username
    site_url = os.environ.get('SITE_URL', 'http://localhost:8000')
    admin_url = f'{site_url}/memorial-admin/main/order/{order.id}/change/'

    msg = MIMEMultipart('alternative')
    msg['To'] = owner_email
    msg['From'] = 'mmsantelopevalley@gmail.com'
    msg['Subject'] = f'🛒 NEW ORDER #{order.id} — {order.get_tier_display()} (${order.tier_price_cents() // 100})'

    text_body = f"""NEW ORDER RECEIVED — Memorial Media Services

Order #{order.id}
Tier: {order.get_tier_display()}
Customer: {user_name} ({order.user.email})
Ordered: {order.created_at.strftime('%B %d, %Y at %I:%M %p')}

{'-' * 40}
TO DO:
1. Log into the admin panel: {admin_url}
2. Review the order details and funeral information
3. Wait for the customer to upload photos
4. Create their tribute slideshow
5. Mark it complete when done

New order total: ${order.tier_price_cents() // 100}
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f5f0eb;margin:0;padding:0;">
<table cellpadding="0" cellspacing="0" width="100%" style="max-width:600px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
<tr><td style="background:linear-gradient(135deg,#1a2a3a,#2c3e50);padding:40px 30px;text-align:center;">
<h1 style="color:#c9a84c;margin:0 0 8px;font-size:28px;">🛒 New Order #{order.id}</h1>
<p style="color:#fff;margin:0;font-size:15px;">A customer just placed an order!</p>
</td></tr>
<tr><td style="padding:30px;">
<table cellpadding="8" cellspacing="0" width="100%" style="font-size:15px;">
<tr><td style="color:#666;width:120px;"><strong>Package</strong></td><td style="color:#333;"><strong>{order.get_tier_display()}</strong></td></tr>
<tr><td style="color:#666;"><strong>Customer</strong></td><td style="color:#333;">{user_name}</td></tr>
<tr><td style="color:#666;"><strong>Email</strong></td><td style="color:#333;">{order.user.email}</td></tr>
<tr><td style="color:#666;"><strong>Date</strong></td><td style="color:#333;">{order.created_at.strftime('%B %d, %Y at %I:%M %p')}</td></tr>
<tr><td style="color:#666;"><strong>Status</strong></td><td style="color:#27ae60;"><strong>✓ PAID</strong></td></tr>
</table>
<div style="background:#f8f4ef;border-radius:8px;padding:20px;margin-top:20px;border-left:4px solid #c9a84c;">
<p style="margin:0 0 10px;color:#333;"><strong>Next steps:</strong></p>
<ol style="margin:0;color:#555;font-size:14px;line-height:1.8;">
<li>Log into the admin panel</li>
<li>Review order details and funeral info</li>
<li>Wait for customer photo uploads</li>
<li>Create the tribute slideshow</li>
<li>Mark complete when done</li>
</ol>
<p style="margin:15px 0 0;"><a href="{admin_url}" style="background:#1a2a3a;color:#c9a84c;text-decoration:none;padding:12px 28px;border-radius:8px;font-size:14px;display:inline-block;">Open Order in Admin</a></p>
</div>
</td></tr>
<tr><td style="background:#f5f0eb;padding:20px 30px;text-align:center;color:#999;font-size:12px;">
Memorial Media Services — You're doing great work.
</td></tr>
</table>
</body>
</html>"""

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    # Channel 1: Gmail API
    ok1, err1 = _send_via_gmail(msg)
    if ok1:
        _log_alert('owner_gmail', order.id, 'sent')
        return True, 'Sent via Gmail API'

    # Channel 2: SMTP fallback (if configured)
    ok2, err2 = _send_via_smtp(msg)
    if ok2:
        _log_alert('owner_smtp', order.id, 'sent (Gmail API failed: %s)' % err1)
        return True, 'Sent via SMTP fallback'

    # Both failed — durable log record so the alert is never lost silently
    _log_alert('owner_gmail', order.id, 'FAILED: %s' % err1)
    _log_alert('owner_smtp', order.id, 'FAILED: %s' % err2)
    return False, f'Both channels failed. Gmail: {err1} | SMTP: {err2}'


def send_simple_email(to_email, subject, body_text):
    """One-off plain-text email via the dual-channel helper (Gmail API -> SMTP)."""
    msg = MIMEMultipart('alternative')
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body_text, 'plain'))
    return _send_via_gmail(msg)
