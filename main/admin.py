import zipfile
from io import BytesIO

from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from .models import Photo, Order, SlideShow, ContactMessage, Cart, CartItem

# Brand the admin
admin.site.site_header = 'Memorial Media Services'
admin.site.site_title = 'Memorial Media Services'
admin.site.index_title = 'Dashboard'


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
    list_display = ['id', 'user', 'deceased_name', 'tier', 'status', 'created_at']
    list_filter = ['status', 'tier']
    search_fields = ['user__username', 'deceased_name']
    readonly_fields = ['stripe_payment_intent']
    actions = ['mark_paid', 'mark_processing', 'mark_completed']
    fieldsets = (
        (None, {'fields': ('user', 'tier', 'status', 'stripe_payment_intent')}),
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
    )

    @admin.action(description='Mark selected as Paid')
    def mark_paid(self, request, queryset):
        queryset.update(status='paid')

    @admin.action(description='Mark selected as In Production')
    def mark_processing(self, request, queryset):
        queryset.update(status='processing')

    @admin.action(description='Mark selected as Completed')
    def mark_completed(self, request, queryset):
        queryset.update(status='completed')


@admin.register(SlideShow)
class SlideShowAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['title', 'user__username']
    actions = ['mark_generating', 'mark_completed_with_notification', 'mark_failed']
    fieldsets = (
        (None, {'fields': ('title', 'user', 'order', 'status')}),
        ('Media Files', {'fields': ('video_file', 'pdf_file'), 'description': 'Upload the finished tribute video and memorial flyer PDF here.'}),
        ('Details', {'fields': ('music_choice', 'error_message', 'photos')}),
    )
    filter_horizontal = ['photos']

    @admin.action(description='Mark selected as Generating')
    def mark_generating(self, request, queryset):
        queryset.update(status='generating')

    @admin.action(description='📧 Mark Completed & Notify Customer')
    def mark_completed_with_notification(self, request, queryset):
        for slideshow in queryset:
            slideshow.status = 'completed'
            slideshow.save()
            # Send notification email to customer
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
    list_display = ['name', 'email', 'service', 'created_at']
    list_filter = ['service', 'created_at']
    search_fields = ['name', 'email', 'message']
    readonly_fields = ['name', 'email', 'service', 'message', 'created_at']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'item_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username']


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'cart', 'tier', 'quantity', 'total_cents']
    list_filter = ['tier']
    search_fields = ['cart__user__username']
