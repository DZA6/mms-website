# Django Security Hardening Guide — Memorial Media Services

**Target:** Django 5.2 / 6.0 | **Site:** Memorial Media Services | **Date:** 2026-07-26

This document covers ALL security measures a production Django site should implement, with specific code snippets and config changes for this project.

---

## Table of Contents

1. [Cryptographic Key Management](#1-cryptographic-key-management)
2. [HTTPS & HSTS](#2-https--hsts)
3. [CSRF Protection](#3-csrf-protection)
4. [XSS Prevention](#4-xss-prevention)
5. [SQL Injection Prevention](#5-sql-injection-prevention)
6. [Clickjacking Protection](#6-clickjacking-protection)
7. [Host Header Validation](#7-host-header-validation)
8. [Session Security](#8-session-security)
9. [Password Policies & Auth Hardening](#9-password-policies--auth-hardening)
10. [Rate Limiting & Brute Force Protection](#10-rate-limiting--brute-force-protection)
11. [Security Headers (HSTS, CSP, Referrer-Policy, COOP)](#11-security-headers)
12. [Secure Cookies](#12-secure-cookies)
13. [File Upload Hardening](#13-file-upload-hardening)
14. [Admin Panel Hardening](#14-admin-panel-hardening)
15. [Stripe Webhook Security](#15-stripe-webhook-security)
16. [Error Handling & Debug Mode](#16-error-handling--debug-mode)
17. [Database Security](#17-database-security)
18. [Logging & Monitoring](#18-logging--monitoring)
19. [Production Middleware Ordering](#19-production-middleware-ordering)
20. [Deployment Checklist Summary](#20-deployment-checklist-summary)

---

## 1. Cryptographic Key Management

### Current State (settings.py lines 26-29)
```python
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-fmlk*=ob%&&$iv+bl()ifr-15(_j5)f(1!tnkts^y6co&#zw*f'
)
```
✅ **Good:** Loaded from env var, has fallback for dev.

### Production Requirements
- **Minimum 50 characters** with letters, digits, symbols (Django check --deploy warns if < 50)
- **Never commit to source control**
- **Rotate immediately if exposed** (note: invalidates sessions, password reset tokens)
- **Generate with:** `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`

### Production Config
```python
# settings.py — production
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']  # No fallback — must be set in prod

# Key rotation support (Django 4.1+)
SECRET_KEY_FALLBACKS = []  # Add old keys during rotation, remove after sessions expire
```

---

## 2. HTTPS & HSTS

### Current State (settings.py lines 183, 187, 193-196)
```python
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
```

### Production Requirements

#### SSL Redirect
```python
# Force all HTTP → HTTPS
SECURE_SSL_REDIRECT = True  # 301 permanent redirect
```

#### If behind a reverse proxy (nginx, Cloudflare, etc.)
```python
# Tell Django the original protocol
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# ⚠️ CRITICAL: Must be set correctly — wrong config creates CSRF vulnerability
# ⚠️ Never trust X-Forwarded-Proto from external sources
```

#### HSTS (HTTP Strict Transport Security)
Gradually increase the `max-age` after verifying HTTPS works:

| Phase | `SECURE_HSTS_SECONDS` | Duration | Notes |
|-------|----------------------|----------|-------|
| Initial | 3600 | 1 hour | Test that HTTPS works perfectly |
| Week 2 | 15768000 | 6 months | After monitoring |
| Final | 31536000 | 1 year | Production target |

```python
SECURE_HSTS_SECONDS = 31536000        # 1 year — final production value
SECURE_HSTS_INCLUDE_SUBDOMAINS = True  # Apply to all subdomains
SECURE_HSTS_PRELOAD = True             # Allow browser preload lists
```

#### Nginx/Apache-level HTTPS config (recommended over Django's redirect)
```nginx
# nginx — stronger than Django-level redirect
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    # ... SSL certs, proxy to Django
}
```

---

## 3. CSRF Protection

### Current State (settings.py lines 186-188)
```python
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = not DEBUG
CSRF_USE_SESSIONS = True
```
✅ **Good:** `CSRF_USE_SESSIONS=True` stores token in session (stronger than separate cookie). `CSRF_COOKIE_HTTPONLY=True` prevents JS access.

### Production Requirements
```python
# Production settings
CSRF_COOKIE_SECURE = True     # HTTPS only
CSRF_COOKIE_HTTPONLY = True   # No JS access
CSRF_USE_SESSIONS = True      # Store in session, not separate cookie
CSRF_COOKIE_SAMESITE = 'Lax'  # Default — reasonable protection
```

### Template Checks
- ✅ All forms use `{% csrf_token %}`
- ✅ Logout form uses POST with CSRF token (base.html line 80)
- ✅ Contact form uses POST with CSRF token (index.html line 284)

### CSRF Exempt Views — Audited
- `stripe_webhook` (views.py line 185) — correctly exempted
  - Uses `@csrf_exempt` — **required** for external webhooks
  - Signature verification happens via `stripe.Webhook.construct_event()` before any state change
  - ✅ **Secure by design**

### Additional Protection
```python
# Prevent CSRF on GET requests that have side effects (Django default protects POST)
# Add this if you have any unsafe GET handlers:
from django.views.decorators.csrf import csrf_protect

# For AJAX, include CSRF token in headers:
# <script>
#   const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
#   fetch('/endpoint/', { method: 'POST', headers: {'X-CSRFToken': csrftoken} });
# </script>
```

---

## 4. XSS Prevention

### Current State
✅ Django templates auto-escape `{{ variables }}` — all templates use this
✅ All forms use Django forms/validation
✅ No unescaped `safe` filter usage found in templates

### Production Requirements

#### Built-in protection (Django does this automatically)
```python
# Auto-escaped characters in templates:
# & → &amp;
# < → &lt;
# > → &gt;
# " → &quot;
# ' → &#x27;
```

#### Watch out for these XSS vectors
```python
# ❌ DANGEROUS — never do these with user data:
{{ user_input|safe }}           # Disables auto-escape
{{ user_input|default:'' }}     # Safe — default is not marked safe
{{ obj.html_field }}            # Safe if field is plain text, dangerous if HTML

# ✅ Safe alternatives for known-safe HTML (markdown, etc.):
# Use a dedicated sanitizer like django-bleach or nh3
# pip install django-bleach
# settings.py:
#   BLEACH_ALLOWED_TAGS = ['p', 'b', 'i', 'em', 'strong', 'a']
#   BLEACH_ALLOWED_ATTRS = {'a': ['href', 'title', 'rel']}
# Template:
#   {{ user_content|bleach }}
```

#### Context-dependent escaping
```python
# For JavaScript context — use json_script filter
# Template: {{ user_data|json_script:"my-data" }}
# JS: const data = JSON.parse(document.getElementById('my-data').textContent);

# For URL context
# Template: <a href="{{ url|urlencode }}">link</a>

# For CSS context — avoid user input entirely, use classes instead
# ❌ <div style="background: {{ user_color }}">  — XSS risk
# ✅ <div class="color-{{ user_choice }}">  — controlled via CSS classes
```

#### Content Security Policy (see Section 11)
CSP is the strongest defense against XSS. Install `django-csp`.

---

## 5. SQL Injection Prevention

### Current State
✅ Django ORM uses parameterized queries — all Querysets are safe
✅ No raw SQL found in views.py or models.py

### Production Requirements

#### Django ORM is safe by default
```python
# ✅ Safe — Django parameterizes the query
Photo.objects.filter(user=request.user, title__contains=search_term)

# ❌ DANGEROUS — never use string formatting in raw SQL
# NEVER DO THIS:
# cursor.execute(f"SELECT * FROM photos WHERE title = '{user_input}'")
```

#### If raw SQL is ever needed
```python
from django.db import connection

def safe_raw_query(user_input):
    with connection.cursor() as cursor:
        # ✅ Safe — pass params separately
        cursor.execute(
            "SELECT * FROM photos WHERE title = %s",
            [user_input]
        )
        return cursor.fetchall()

# ORM alternatives that look dangerous but are actually parameterized:
# Photo.objects.extra(where=["title LIKE %s"], params=[f'%{search}%'])  # Safe
# Photo.objects.annotate(...)  # Safe
```

#### Current project audit
- ✅ `get_object_or_404(Order, id=order_id, user=request.user)` — safe, uses ORM
- ✅ `Photo.objects.filter(user=request.user)` — safe
- ✅ `Order.objects.create(...)` — safe
- ✅ `SlideShow.objects.create(...)` — safe
- ✅ `SlideShow.objects.filter(order=order)` — safe
- ⚠️ **Contact form** stores data in memory only (no DB) — verify no SQL used

---

## 6. Clickjacking Protection

### Current State (settings.py line 190)
```python
X_FRAME_OPTIONS = 'DENY'
```
✅ **Good:** Blocks all framing.

### Production Requirements
```python
X_FRAME_OPTIONS = 'DENY'          # Default — block all framing
# X_FRAME_OPTIONS = 'SAMEORIGIN'  # Only if you need <iframe> on your own domain

# XFrameOptionsMiddleware must be in MIDDLEWARE (line 59) ✅
```

### Per-view override (if ever needed)
```python
from django.views.decorators.clickjacking import xframe_options_exempt, xframe_options_sameorigin

@xframe_options_sameorigin
def embeddable_view(request):
    ...

@xframe_options_exempt
def embeddable_anywhere_view(request):
    ...
```

---

## 7. Host Header Validation

### Current State (settings.py line 36)
```python
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') \
    if os.environ.get('DJANGO_ALLOWED_HOSTS') \
    else ['localhost', '127.0.0.1']
```
✅ **Good:** Loaded from env var, falls back to localhost for dev.

### Production Requirements
```python
# Production — set DJANGO_ALLOWED_HOSTS env var
# ALLOWED_HOSTS = 'yourdomain.com,www.yourdomain.com'

# ❌ NEVER use wildcard ('*') — opens to host header attacks
# ALLOWED_HOSTS = ['*']  # INSECURE

# ✅ Bonus: validate at the reverse proxy level (nginx)
# server {
#     listen 80 default_server;
#     return 444;  # Drop requests with unknown hosts
# }
```

### ⚠️ Important: about request.build_absolute_uri
The base.html template uses `{{ request.build_absolute_uri }}` in canonical URLs and OG tags (lines 11, 18). With `ALLOWED_HOSTS` set, Django already validates the Host header before `request.build_absolute_uri()` is callable, so this is **safe**.

---

## 8. Session Security

### Current State (settings.py lines 180-184)
```python
SESSION_COOKIE_AGE = 86400           # 24 hours
SESSION_COOKIE_HTTPONLY = True       # No JS access
SESSION_COOKIE_SECURE = not DEBUG    # HTTPS only in prod
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True    # Refresh expiry on each request
```
✅ **Good** configuration.

### Production Requirements
```python
SESSION_COOKIE_SECURE = True          # HTTPS only
SESSION_COOKIE_HTTPONLY = True        # No JS access
SESSION_COOKIE_AGE = 86400            # 24 hours (adjust as needed)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Logout on browser close
SESSION_SAVE_EVERY_REQUEST = True     # Slide expiry forward
SESSION_COOKIE_SAMESITE = 'Lax'       # CSRF defense (Django 3.1+)

# Session engine — use Redis for production
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# OR (more reliable):
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
# Cookie-based — fast but 4KB size limit, all session data in browser cookie
```

### Session Hijacking Prevention
```python
# Invalidate session on password change (Django does this automatically)
# settings.py:
#   PASSWORD_CHANGE_SESSION_HASH = True  # Django 5.2+

# Logout should invalidate the session
# In views, use:
#   from django.contrib.auth import logout
#   logout(request)  # Clears session
# ✅ Signup view calls login() which creates a new session (line 63)
# ✅ Logout uses Django's LogoutView (urls.py line 14) — clears session
```

---

## 9. Password Policies & Auth Hardening

### Current State (settings.py lines 130-138)
```python
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
```
✅ **Good:** Minimum 10 characters, blocks common passwords, blocks numeric-only, checks similarity.

### Production Enhancement
```python
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        'OPTIONS': {
            'user_attributes': ('username', 'email', 'first_name', 'last_name'),
            'max_similarity': 0.7,
        },
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},  # Bumped from 10 to 12
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Password hashing — ensure strongest algorithm is first
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',          # Strongest
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',          # Default
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.ScryptPasswordHasher',
]
```

### Install argon2 for strongest hashing
```bash
pip install django[argon2]
# or
pip install argon2-cffi
```

---

## 10. Rate Limiting & Brute Force Protection

### Current State
✅ `django_ratelimit` installed
✅ Login view rate-limited to 10/hour per IP (views.py line 51)
✅ Signup view rate-limited to 10/hour per IP (views.py line 57)

### Production Enhancement

#### Install django-axes for account lockout (recommended addition)
```bash
pip install django-axes
```

```python
# settings.py additions for django-axes
INSTALLED_APPS = [
    ...
    'django_ratelimit',
    'axes',  # Account lockout after N failed attempts
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'axes.middleware.AxesMiddleware',  # After SecurityMiddleware, before session
    ...
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',  # Must be first
    'django.contrib.auth.backends.ModelBackend',
]

# Axes configuration
AXES_FAILURE_LIMIT = 5          # Lock after 5 failed attempts
AXES_COOLOFF_TIME = 1           # Hours locked out
AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True  # Lock per-user+IP
AXES_RESET_ON_SUCCESS = True    # Reset counter on successful login
AXES_ENABLE_ADMIN = True        # View lockouts in admin
```

#### Broader rate limiting
```python
# Rate limit ALL auth-related views
from django_ratelimit.decorators import ratelimit
from django_ratelimit import UNSAFE

@ratelimit(key='ip', rate='10/h', method=UNSAFE, block=True)
def custom_login(request):
    """Rate-limited login view."""
    return LoginView.as_view(template_name='login.html')(request)

@ratelimit(key='ip', rate='5/h', method=UNSAFE, block=True)
def signup(request):
    # Tighter limit on signup — prevent account creation spam
    ...

# Password reset — also rate limit
# You may need a custom view wrapping PasswordResetView
```

#### Cache backend for rate limiting
```python
# Current (dev) — LocMemCache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Production — Redis (required for multi-process/load-balanced deployments)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    }
}
```

---

## 11. Security Headers

### Current State (settings.py lines 191-192)
```python
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
```

### Complete Security Headers Configuration

```python
# === REQUIRED HEADERS ===

# Prevent MIME type sniffing
SECURE_CONTENT_TYPE_NOSNIFF = True          # X-Content-Type-Options: nosniff

# Legacy XSS filter (deprecated in modern browsers, but harmless)
SECURE_BROWSER_XSS_FILTER = True            # X-XSS-Protection: 1; mode=block

# Clickjacking
X_FRAME_OPTIONS = 'DENY'                    # X-Frame-Options: DENY

# HSTS
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Referrer Policy — control what info is sent in the Referer header
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
# Options: 'same-origin', 'strict-origin', 'strict-origin-when-cross-origin'

# Cross-origin Opener Policy — protect against cross-origin attacks
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'
# Options: 'same-origin' (strict), 'same-origin-allow-popups' (balanced), 'unsafe-none'

# === CONTENT SECURITY POLICY (django-csp) ===

# Install: pip install django-csp
INSTALLED_APPS = [
    ...
    'csp',
]

MIDDLEWARE = [
    'csp.middleware.CSPMiddleware',
    ...
]

CSP_DEFAULT_SRC = ("'none'",)                          # Deny everything not listed
CSP_SCRIPT_SRC = ("'self'", "https://js.stripe.com")   # Stripe.js
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")          # Inline styles needed
CSP_IMG_SRC = ("'self'", "data:", "https:")            # Self + data URIs + HTTPS images
CSP_FONT_SRC = ("'self'",)                             # Self-hosted fonts
CSP_CONNECT_SRC = ("'self'", "https://api.stripe.com")  # Stripe API
CSP_FRAME_SRC = ("'self'", "https://js.stripe.com")    # Stripe iframe
CSP_MEDIA_SRC = ("'self'",)                             # Video/audio
CSP_OBJECT_SRC = ("'none'",)                           # No plugins
CSP_BASE_URI = ("'self'",)                             # Base tag limit
CSP_FORM_ACTION = ("'self'",)                          # Form submission target

# CSP report-uri (optional, for monitoring violations)
CSP_REPORT_URI = "/csp-violation-report/"  # Or use report-uri.com
```

---

## 12. Secure Cookies

### Current State
```python
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
```

### Production Requirements
```python
# All cookies must be:
# 1. SECURE — only sent over HTTPS
# 2. HTTPONLY — not accessible to JavaScript (prevents XSS cookie theft)
# 3. SAMESITE — limited cross-origin sending

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Any custom cookies set via HttpResponse.set_cookie():
from django.http import HttpResponse

def my_view(request):
    response = HttpResponse(...)
    response.set_cookie(
        'my_cookie',
        'value',
        secure=True,       # HTTPS only
        httponly=True,     # No JS access
        samesite='Lax',    # CSRF defense
        max_age=86400,     # Expiry
    )
    return response
```

---

## 13. File Upload Hardening

### Current State
- ✅ 60 MB upload limit (settings.py lines 163-164)
- ✅ Per-user count cap of 60 photos (views.py line 86)
- ✅ ImageField already validates via Pillow
- ✅ `accept="image/*"` on HTML input (upload.html line 42)

### Additional Hardening

#### Validate file type server-side
```python
# In upload view (or form clean method)
import imghdr  # Python 3.6+
# or use: from PIL import Image

def validate_image(file):
    """Validate that uploaded file is actually an image."""
    try:
        from PIL import Image
        img = Image.open(file)
        img.verify()  # Raises exception if not a valid image
        file.seek(0)  # Reset file pointer
        return True
    except Exception:
        return False
```

#### Prevent upload of HTML disguised as images
```python
# Note from Django docs: An HTML file can be uploaded as an image if
# it contains a valid PNG header followed by malicious HTML.
# Pillow only validates the header, not the entire file.

# Mitigation:
# 1. Serve uploaded content from a separate domain (MEDIA_URL on different domain)
# 2. Configure nginx to never execute uploaded files
# 3. Use whitehat analysis: python3 -c "from PIL import Image; Image.open(file)" 
#    and check file extension matches

# nginx — disable execution in media directory
# location /media/ {
#     alias /path/to/media/;
#     location ~ \.(php|py|pl|cgi)$ { deny all; }
# }
```

#### File extension whitelist
```python
# In form's clean method
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

import os
def clean_images(self):
    images = self.cleaned_data.get('images', [])
    for img in images:
        ext = os.path.splitext(img.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError(f"Unsupported file type: {ext}")
    return images
```

#### Production media serving config
```nginx
# nginx — media files served directly (not through Django)
location /media/ {
    alias /path/to/media/;
    expires 30d;
    add_header Cache-Control "public, immutable";
    
    # Block execution
    location ~ \.(php|py|pl|cgi|asp|aspx|sh)$ {
        deny all;
    }
}
```

---

## 14. Admin Panel Hardening

### Current State
✅ Admin URL changed from `/admin/` to `/memorial-admin/` (urls.py line 9)
✅ Custom branding set (from django-web-app skill)

### Additional Hardening

#### Non-standard URL (already done)
```python
# urls.py
path('memorial-admin/', admin.site.urls),  # NOT 'admin/'
```

#### Custom branding
```python
# admin.py (already configured via django-web-app skill pattern)
admin.site.site_header = 'Memorial Media Services'
admin.site.site_title = 'Memorial Media Services'
admin.site.index_title = 'Dashboard'
```

#### IP restriction (nginx level)
```nginx
# nginx — restrict admin to office IPs only
location /memorial-admin/ {
    allow YOUR.OFFICE.IP.HERE;
    deny all;
    proxy_pass http://django_app;
}
```

#### Additional admin protections
```python
# Force HTTPS for admin sessions
# (already covered by SECURE_SSL_REDIRECT)
```

---

## 15. Stripe Webhook Security

### Current State (views.py lines 185-218)
```python
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)
    ...
    return HttpResponse(status=200)
```
✅ **Good:** Signature verification before any state change. Returns 200 to acknowledge receipt.

### Production Requirements
```python
# Additional hardening:

# 1. Verify endpoint_secret is always set in production
endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
if not endpoint_secret:
    return HttpResponse(status=500)  # Don't process without secret

# 2. Rate-limit the webhook endpoint
# Stripe will retry with backoff, so rate-limiting is optional but defensive

# 3. Use idempotency with Stripe events
# (Stripe sends events at least once — handle duplicates)
processed_events = set()  # Or cache-backed
if intent['id'] in processed_events:
    return HttpResponse(status=200)  # Already processed
processed_events.add(intent['id'])

# 4. Validate webhook payload size
if len(payload) > 1_000_000:  # 1MB maximum
    return HttpResponse(status=413)
```

---

## 16. Error Handling & Debug Mode

### Current State
```python
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')
```
✅ **Good:** DEBUG controlled by env var, defaults to True for dev.

### Production Requirements
```python
# Production — set DJANGO_DEBUG=False
# NEVER DEBUG = True in production — it leaks:
#   - Source code excerpts
#   - Local variables
#   - Settings (including SECRET_KEY through backtraces)
#   - Database credentials
#   - Library versions with known vulnerabilities

# Custom error pages
handler404 = 'main.views.custom_404'
handler500 = 'main.views.custom_500'
handler403 = 'main.views.custom_403'
handler400 = 'main.views.custom_400'
```

```python
# views.py — custom error handlers (prevent information leakage)
def custom_404(request, exception):
    return render(request, '404.html', status=404)

def custom_500(request):
    return render(request, '500.html', status=500)

def custom_403(request, exception):
    return render(request, '403.html', status=403)

def custom_400(request, exception):
    return render(request, '400.html', status=400)
```

```html
<!-- templates/404.html — extend base.html -->
{% extends 'base.html' %}
{% block content %}
<div class="auth-page">
    <div class="auth-card" style="text-align:center;">
        <h1>Page Not Found</h1>
        <p>The page you're looking for doesn't exist. It may have been moved or deleted.</p>
        <a href="{% url 'home' %}" class="btn btn-primary">Go Home</a>
    </div>
</div>
{% endblock %}
```

### Error Reporting
```python
# Production error reporting
ADMINS = [('Your Name', 'admin@yourdomain.com')]  # Gets 500 error emails
MANAGERS = [('Your Name', 'admin@yourdomain.com')]  # Gets 404 error emails

# Better: Use Sentry for error aggregation
# pip install sentry-sdk
# import sentry_sdk
# sentry_sdk.init(dsn=os.environ['SENTRY_DSN'])
```

---

## 17. Database Security

### Current State (settings.py lines 89-112)
✅ Falls back to SQLite for dev
✅ PostgreSQL supported via DATABASE_URL
✅ dj-database-url for production parsing

### Production Requirements
```python
# PostgreSQL — always use connection pooling
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],  # Never hardcode
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,  # Connection persistence — 10 minutes
        'OPTIONS': {
            'sslmode': 'require',  # Encrypt database connections
        },
    }
}
```

### Additional Database Hardening
```python
# Never use the database superuser for the web app
# Create a dedicated user with limited privileges:
#   CREATE USER django_user WITH PASSWORD 'strong_password';
#   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO django_user;
#   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO django_user;

# Firewall — only accept DB connections from app servers
# On PostgreSQL: listen_addresses = 'app.internal.ip'
```

---

## 18. Logging & Monitoring

### Production Logging Configuration
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs/django.log',
            'formatter': 'verbose',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'mail_admins'],
            'level': 'WARNING',
            'propagate': True,
        },
        'django.security': {
            'handlers': ['file', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# Create the logs directory
# mkdir -p logs
# chmod 750 logs
```

---

## 19. Production Middleware Ordering

### Current State (settings.py lines 52-60)
```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',          # 1 — Security headers
    'django.contrib.sessions.middleware.SessionMiddleware',   # 2 — Session
    'django.middleware.common.CommonMiddleware',               # 3 — Common
    'django.middleware.csrf.CsrfViewMiddleware',               # 4 — CSRF
    'django.contrib.auth.middleware.AuthenticationMiddleware', # 5 — Auth
    'django.contrib.messages.middleware.MessageMiddleware',    # 6 — Messages
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # 7 — Clickjacking
]
```
✅ **Good:** Django-recommended order.

### Production Ordering (with extra packages)
```python
MIDDLEWARE = [
    'csp.middleware.CSPMiddleware',                           # 0 — CSP before everything
    'django.middleware.security.SecurityMiddleware',          # 1 — Security headers
    'axes.middleware.AxesMiddleware',                         # 2 — Account lockout
    'django.contrib.sessions.middleware.SessionMiddleware',   # 3 — Session
    'django.middleware.common.CommonMiddleware',               # 4 — Common
    'django.middleware.csrf.CsrfViewMiddleware',               # 5 — CSRF
    'django.contrib.auth.middleware.AuthenticationMiddleware', # 6 — Auth
    'django.contrib.messages.middleware.MessageMiddleware',    # 7 — Messages
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # 8 — Clickjacking
]
```

---

## 20. Deployment Checklist Summary

### Run this command immediately
```bash
python manage.py check --deploy
```

### All Settings to Toggle for Production

| Setting | Dev | Production | Why |
|---------|-----|-----------|-----|
| `DEBUG` | `True` | `False` | Info leakage |
| `SECRET_KEY` | Env fallback | Env only, 50+ chars | Crypto security |
| `ALLOWED_HOSTS` | localhost | `['yourdomain.com']` | Host header validation |
| `SESSION_COOKIE_SECURE` | `False` | `True` | HTTPS-only session |
| `CSRF_COOKIE_SECURE` | `False` | `True` | HTTPS-only CSRF |
| `SECURE_SSL_REDIRECT` | `False` | `True` | Force HTTPS |
| `SECURE_HSTS_SECONDS` | `0` | `31536000` | HSTS (after testing) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | `True` | HSTS subdomains |
| `SECURE_HSTS_PRELOAD` | `False` | `True` | Browser preload |
| `CACHES` | LocMemCache | Redis | Rate limiting, sessions |
| `SECURE_PROXY_SSL_HEADER` | Not set | Config as needed | Behind proxy |
| `DATABASES` | SQLite | PostgreSQL | Production durability |
| `EMAIL_BACKEND` | Console | SMTP | Real email |

### One-Time Production Setup
```bash
# 1. Generate strong secret key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 2. Set required env vars
export DJANGO_SECRET_KEY='<generated_key>'
export DJANGO_DEBUG='False'
export DJANGO_ALLOWED_HOSTS='yourdomain.com,www.yourdomain.com'
export DATABASE_URL='postgres://user:pass@host/db'
export REDIS_URL='redis://localhost:6379/0'
export STRIPE_SECRET_KEY='sk_live_...'
export STRIPE_PUBLISHABLE_KEY='pk_live_...'
export STRIPE_WEBHOOK_SECRET='whsec_...'

# 3. Install additional packages
pip install django-axes django-csp argon2-cffi psycopg2-binary
pip install sentry-sdk  # Optional error monitoring

# 4. Run security check
python manage.py check --deploy

# 5. Collect static files
python manage.py collectstatic --noinput

# 6. Create error page templates
# templates/404.html, templates/500.html, templates/403.html, templates/400.html
```

### What's Already Done (✅)

| Feature | Status | Notes |
|---------|--------|-------|
| CSRF protection | ✅ | All forms have `{% csrf_token %}`, `CSRF_USE_SESSIONS=True` |
| Session security | ✅ | HTTPOnly, Secure in prod, expiry, browser-close |
| Password validators | ✅ | Min 10 length, common pw check, similarity check |
| Rate limiting | ✅ | Login & signup limited to 10/hour |
| Clickjacking | ✅ | `X_FRAME_OPTIONS = 'DENY'` |
| MIME sniffing | ✅ | `SECURE_CONTENT_TYPE_NOSNIFF = True` |
| XSS filter header | ✅ | `SECURE_BROWSER_XSS_FILTER = True` |
| Template escaping | ✅ | Django auto-escapes all `{{ var }}` |
| SQL injection | ✅ | ORM only, no raw SQL |
| Secret key management | ✅ | Environment variable, not hardcoded |
| Admin URL obfuscation | ✅ | `/memorial-admin/` not `/admin/` |
| Stripe webhook | ✅ | Signature verification before processing |
| Upload limits | ✅ | 60 MB file, 60 photos/user |

### What Needs Attention (⚠️)

| Feature | Status | Action Needed |
|---------|--------|--------------|
| HSTS | ⚠️ | Set `SECURE_HSTS_SECONDS` > 0 after HTTPS confirmed working |
| CSP | ⚠️ | Install `django-csp`, configure policy |
| Account lockout | ⚠️ | Install `django-axes` for brute-force protection |
| Password hasher | ⚠️ | Install `argon2-cffi`, add `Argon2PasswordHasher` |
| Session engine | ⚠️ | Switch to Redis cache backend |
| Error pages | ⚠️ | Create `404.html`, `500.html`, `403.html`, `400.html` |
| Referrer Policy | ⚠️ | Add `SECURE_REFERRER_POLICY` |
| Cross-Origin Opener Policy | ⚠️ | Add `SECURE_CROSS_ORIGIN_OPENER_POLICY` |
| File server hardening | ⚠️ | Configure nginx to block execution in `/media/` |
| Error monitoring | ⚠️ | Set up Sentry or logging to file |
| Database SSL | ⚠️ | Set `sslmode: 'require'` in PostgreSQL config |
| Custom error handlers | ⚠️ | Add `handler404`, `handler500`, etc. |

---

## References

- [OWASP Django Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Django_Security_Cheat_Sheet.html)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Django Security Topics](https://docs.djangoproject.com/en/5.2/topics/security/)
- [Django CSRF Protection](https://docs.djangoproject.com/en/5.2/ref/csrf/)
- [Django Clickjacking Protection](https://docs.djangoproject.com/en/5.2/ref/clickjacking/)
- [Django Session Security](https://docs.djangoproject.com/en/5.2/topics/http/sessions/#security)
- [django-axes Documentation](https://django-axes.readthedocs.io/)
- [django-csp Documentation](https://django-csp.readthedocs.io/)
- [Mozilla Web Security](https://infosec.mozilla.org/guidelines/web_security)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
