from django.conf import settings

def contact_info(request):
    """Make contact info available to all templates for schema.org markup."""
    return {
        'CONTACT_PHONE': getattr(settings, 'CONTACT_PHONE', '(555) 123-4567'),
        'CONTACT_EMAIL': getattr(settings, 'CONTACT_EMAIL', 'hello@memorialmediaservices.com'),
        'GOOGLE_ANALYTICS_ID': getattr(settings, 'GOOGLE_ANALYTICS_ID', ''),
    }
