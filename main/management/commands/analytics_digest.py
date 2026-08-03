"""Daily business analytics digest for the owner.

Usage:  python manage.py analytics_digest
Emails yesterday's business stats (orders, revenue, customers, pending
work) to OWNER_EMAIL. Designed to run daily via a PythonAnywhere
scheduled task. Reuses the site's Gmail API machinery.
"""
import os
from datetime import timedelta
from email.mime.text import MIMEText

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from main.email_helper import _send_via_gmail
from main.models import ContactMessage, Order, SlideShow

User = get_user_model()


class Command(BaseCommand):
    help = "Email a daily business digest (orders, revenue, customers, pending work)."

    def handle(self, *args, **options):
        now = timezone.now()
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)

        orders = Order.objects.filter(created_at__gte=start, created_at__lt=end)
        paid_orders = orders.exclude(status='pending')
        revenue_cents = sum(o.tier_price_cents() for o in paid_orders)

        new_users = User.objects.filter(date_joined__gte=start, date_joined__lt=end).count()
        new_slideshows = SlideShow.objects.filter(created_at__gte=start, created_at__lt=end).count()
        pending_slideshows = SlideShow.objects.filter(status='pending').count()
        messages = ContactMessage.objects.filter(created_at__gte=start, created_at__lt=end).count()

        body = "\n".join([
            "MEMORIAL MEDIA SERVICES — DAILY DIGEST",
            f"For: {start.strftime('%B %d, %Y')}",
            "",
            f"New orders:          {orders.count()}",
            f"  Basic ($49.99):    {orders.filter(tier='basic').count()}",
            f"  Package ($74.99):  {orders.filter(tier='digital').count()}",
            f"Paid orders:         {paid_orders.count()}",
            f"Revenue:             ${revenue_cents / 100:.2f}",
            "",
            f"New customers:       {new_users}",
            f"Contact messages:    {messages}",
            "",
            f"New slideshows:      {new_slideshows}",
            f"Slideshows pending:  {pending_slideshows}",
            "",
            "Admin panel: https://www.memorialmediaservices.org/memorial-admin/",
        ])

        msg = MIMEText(body, 'plain')
        msg['To'] = os.environ.get('OWNER_EMAIL', 'mmsantelopevalley@gmail.com')
        msg['From'] = 'mmsantelopevalley@gmail.com'
        msg['Subject'] = (
            f"📊 Daily Digest {start.strftime('%b %d')}: "
            f"{orders.count()} orders, ${revenue_cents / 100:.2f}"
        )

        ok, result = _send_via_gmail(msg)
        if ok:
            self.stdout.write(self.style.SUCCESS("Digest sent: " + result))
        else:
            self.stderr.write("Digest FAILED: " + result)
            raise SystemExit(1)
