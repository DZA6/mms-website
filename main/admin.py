import zipfile
from io import BytesIO

from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from .models import Photo, Order, SlideShow

# Brand the admin instead of "Django administration"
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
        """Bundle selected photos into a ZIP file and serve it."""
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for photo in queryset:
                if not photo.image:
                    continue
                try:
                    # Read the file from disk
                    path = photo.image.path
                    arcname = f'{photo.user.username}/{photo.id:04d}_{photo.image.name.split("/")[-1]}'
                    zf.write(path, arcname)
                except Exception:
                    pass  # skip files that can't be read

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="photos_{queryset.count()}_items.zip"'
        return response


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'tier', 'status', 'created_at']
    list_filter = ['status', 'tier']
    search_fields = ['user__username']
    readonly_fields = ['stripe_payment_intent']


@admin.register(SlideShow)
class SlideShowAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['title', 'user__username']
    fieldsets = (
        (None, {
            'fields': ('title', 'user', 'order', 'status')
        }),
        ('Media Files', {
            'fields': ('video_file', 'pdf_file'),
            'description': 'Upload the finished tribute video and memorial flyer PDF here.',
        }),
        ('Details', {
            'fields': ('music_choice', 'error_message', 'photos'),
        }),
    )