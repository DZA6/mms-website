import zipfile
from io import BytesIO

from django.contrib import admin
from django.contrib.auth.models import User
from django.db.models import Sum, Count
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html
from .models import Photo, Order, SlideShow, ContactMessage, Cart, CartItem

# Brand the admin
admin.site.site_header = 'Memorial Media Services'
admin.site.site_title = 'Memorial Media Services'
admin.site.index_title = 'Dashboard'


def _revenue_for_queryset(qs):
    """Sum order values in dollars from tier prices."""
    from main.views import TIER_PRICES
    total = 0
    for o in qs:
        total += TIER_PRICES.get(o.tier, 0)
    return total / 100


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'uploaded_at', 'image_preview', 'download_link']
    list_filter = ['user']
    search_fields = ['title', 'user__username']
    readonly_fields = ['image_preview', 'download_link']
    actions = ['download_selected_as_zip']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:60px;border-radius:4px;">', obj.image.url)
        return '-'
    image_preview.short_description = 'Preview'

    def download_link(self, obj):
        if obj.image:
            return format_html('<a href="{}" download style="background:#1a2a3a;color:#fff;padding:4px 12px;border-radius:4px;text-decoration:none;font-size:0.85rem;">⬇ Download</a>', obj.image.url)
        return '-'
    download_link.short_description = 'Download'

    @admin.action(description='📦 Download selected photos as ZIP')
    def download_selected_as_zip(self, request, queryset):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for photo in queryset:
                if not photo.image:
                    continue
                try:
                    path = photo.image.path
                    arcname = f'{photo.user.username}/{photo.id:04d}_{photo.image.name.split("/")[-1]}'
                    zf.write(path, arcname)
                except Exception:
                    pass
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="photos_{queryset.count()}_items.zip"'
        return response


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'status_badge', 'user', 'deceased_name', 'tier', 'price_display', 'service_date', 'created_at']
    list_filter = ['status', 'tier', 'created_at']
    search_fields = ['user__username', 'deceased_name', 'id']
    readonly_fields = ['stripe_payment_intent', 'price_display']
    date_hierarchy = 'created_at'
    actions = ['mark_paid', 'mark_processing', 'mark_completed']

    def status_badge(self, obj):
        colors = {
            'pending': '#f57f17',      # amber
            'paid': '#1976d2',         # blue — new order, needs attention
            'processing': '#7b1fa2',   # purple — in production
            'completed': '#2e7d32',    # green
        }
        c = colors.get(obj.status, '#666')
        return format_html('<span style="background:{};color:#fff;padding:3px 10px;border-radius:12px;font-size:0.8rem;">{}</span>', c, obj.get_status_display())
    status_badge.short_description = 'Status'

    def price_display(self, obj):
        return f'${obj.price_dollars():.2f}'
    price_display.short_description = 'Price'

    def service_date(self, obj):
        return obj.service_date.strftime('%b %d, %Y') if obj.service_date else '—'
    service_date.short_description = 'Service'

    fieldsets = (
        (None, {'fields': ('user', 'tier', 'status', 'price_display', 'stripe_payment_intent')}),
        ('About the Deceased', {'fields': (
            ('deceased_name',),
            ('date_of_birth', 'date_of_death'),
        )}),
        ('Service Details', {'fields': (
            'service_type',
            ('service_date', 'service_time'),
            'service_location',
            'burial_place',
        )}),
        ('Tribute Preferences', {'fields': (
            'preferred_song',
            'special_notes',
        )}),
        ('Shipping (print orders)', {'fields': (
            ('shipping_name',),
            'shipping_address',
            ('shipping_city', 'shipping_state', 'shipping_zip'),
        )}),
    )

    @admin.action(description='✅ Mark selected as Paid')
    def mark_paid(self, request, queryset):
        queryset.update(status='paid')

    @admin.action(description='🔧 Mark selected as In Production')
    def mark_processing(self, request, queryset):
        queryset.update(status='processing')

    @admin.action(description='🎉 Mark selected as Completed')
    def mark_completed(self, request, queryset):
        queryset.update(status='completed')


@admin.register(SlideShow)
class SlideShowAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'order_link', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['title', 'user__username']
    actions = ['mark_generating', 'mark_completed_with_notification', 'mark_failed']
    fieldsets = (
        (None, {'fields': ('title', 'user', 'order', 'status')}),
        ('Media Files', {'fields': ('video_file', 'pdf_file'), 'description': 'Upload the finished tribute video and memorial flyer PDF here.'}),
        ('Details', {'fields': ('music_choice', 'error_message', 'photos')}),
    )
    filter_horizontal = ['photos']

    def order_link(self, obj):
        if obj.order_id:
            return format_html('<a href="/memorial-admin/main/order/{}/change/">Order #{}</a>', obj.order_id, obj.order_id)
        return '—'
    order_link.short_description = 'Order'

    @admin.action(description='Mark selected as Generating')
    def mark_generating(self, request, queryset):
        queryset.update(status='generating')

    @admin.action(description='📧 Mark Completed & Notify Customer')
    def mark_completed_with_notification(self, request, queryset):
        for slideshow in queryset:
            slideshow.status = 'completed'
            slideshow.save()
            try:
                from .email_helper import send_completion_email
                success, msg = send_completion_email(slideshow)
                if not success:
                    self.message_user(request, f'Email failed for {slideshow.user}: {msg}', level='ERROR')
                else:
                    self.message_user(request, f'✅ Notified {slideshow.user.email} about #{slideshow.id}')
            except Exception as e:
                self.message_user(request, f'Email error: {e}', level='ERROR')

    @admin.action(description='Mark selected as Failed')
    def mark_failed(self, request, queryset):
        queryset.update(status='failed')


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'service', 'message_preview', 'created_at']
    list_filter = ['service', 'created_at']
    search_fields = ['name', 'email', 'message']
    readonly_fields = ['name', 'email', 'service', 'message', 'created_at']

    def message_preview(self, obj):
        return obj.message[:60] + ('…' if len(obj.message) > 60 else '')
    message_preview.short_description = 'Message'


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'item_count', 'total_display', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username']


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'cart', 'tier', 'quantity', 'total_cents']
    list_filter = ['tier']
    search_fields = ['cart__user__username']


# ------------------------------------------------------------------
# Custom admin dashboard with business stats
# ------------------------------------------------------------------
class MMSAdminSite(admin.AdminSite):
    """Admin site with a custom dashboard index page."""

    def index(self, request, extra_context=None):
        from main.views import TIER_PRICES

        # --- Orders ---
        orders = Order.objects.all()
        paid_orders = orders.filter(status='paid')
        processing_orders = orders.filter(status='processing')
        completed_orders = orders.filter(status='completed')
        pending_orders = orders.filter(status='pending')

        def revenue(qs):
            return sum(TIER_PRICES.get(o.tier, 0) for o in qs) / 100

        # --- New orders needing attention (paid, no deceased name yet) ---
        needs_details = paid_orders.filter(deceased_name='')

        # --- Slideshows ---
        slideshows = SlideShow.objects.all()
        pending_slideshows = slideshows.filter(status='pending')

        # --- Recent contacts ---
        recent_contacts = ContactMessage.objects.all()[:8]

        # --- Stats ---
        stats = {
            'total_orders': orders.count(),
            'total_revenue': revenue(orders),
            'paid_revenue': revenue(paid_orders),
            'paid_count': paid_orders.count(),
            'processing_count': processing_orders.count(),
            'completed_count': completed_orders.count(),
            'pending_count': pending_orders.count(),
            'needs_details_count': needs_details.count(),
            'pending_slideshows_count': pending_slideshows.count(),
            'total_photos': Photo.objects.count(),
            'registered_users': User.objects.count(),
        }

        # --- Recent orders ---
        recent_orders = orders.order_by('-created_at')[:8]

        context = {
            'stats': stats,
            'recent_orders': recent_orders,
            'needs_details': needs_details[:8],
            'pending_slideshows': pending_slideshows[:8],
            'recent_contacts': recent_contacts,
            'title': 'Dashboard',
        }
        if extra_context:
            context.update(extra_context)
        return render(request, 'admin/dashboard.html', context)


# Replace the default admin site
admin_site = MMSAdminSite(name='memorial_admin')
admin_site.register(Photo, PhotoAdmin)
admin_site.register(Order, OrderAdmin)
admin_site.register(SlideShow, SlideShowAdmin)
admin_site.register(ContactMessage, ContactMessageAdmin)
admin_site.register(Cart, CartAdmin)
admin_site.register(CartItem, CartItemAdmin)
