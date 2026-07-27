from django.conf import settings

def contact_info(request):
    """Make contact info available to all templates for schema.org markup."""
    return {
        'CONTACT_PHONE': getattr(settings, 'CONTACT_PHONE', '(661) 271-2148'),
        'CONTACT_EMAIL': getattr(settings, 'CONTACT_EMAIL', 'MMSantelopevalley@gmail.com'),
        'GOOGLE_ANALYTICS_ID': getattr(settings, 'GOOGLE_ANALYTICS_ID', ''),
    }
