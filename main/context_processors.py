from django.conf import settings
import os

def contact_info(request):
    """Make contact info available to all templates for schema.org markup."""
    return {
        'CONTACT_PHONE': getattr(settings, 'CONTACT_PHONE', '(661) 271-2148'),
        'CONTACT_EMAIL': getattr(settings, 'CONTACT_EMAIL', 'MMSantelopevalley@gmail.com'),
        'GOOGLE_ANALYTICS_ID': getattr(settings, 'GOOGLE_ANALYTICS_ID', ''),
    }


def cache_bust(request):
    """Append a content-hash query param to static assets so browsers never
    serve stale cached CSS/JS after a deploy (iOS Safari is aggressive)."""
    result = {}
    for name in ('style_css', 'app_js'):
        result[name] = ''
    try:
        static_root = getattr(settings, 'STATIC_ROOT', '')
        base_dir = getattr(settings, 'BASE_DIR', '')
        candidates = {
            'style_css': [os.path.join(static_root, 'css/style.css'),
                          os.path.join(base_dir, 'static/css/style.css')],
            'app_js': [os.path.join(static_root, 'js/app.js'),
                       os.path.join(base_dir, 'static/js/app.js')],
        }
        for key, paths in candidates.items():
            for p in paths:
                if p and os.path.exists(p):
                    with open(p, 'rb') as f:
                        h = f.read()
                    result[key] = '?v=' + str(abs(hash(h)))[:10]
                    break
    except Exception:
        pass
    return result
