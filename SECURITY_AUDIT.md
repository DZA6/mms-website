# Security Audit — Memorial Media Services (Django 5.2)

**Date:** 2026-07-26
**Target:** `/home/rig/memorial-site/my_website/`
**Stack:** Django 5.2, SQLite (dev), Stripe, File uploads (images/video), User auth

---

## 🔴 Critical Issues (Fix Immediately)

### 1. Hardcoded Fallback Secret Key

**File:** `core/settings.py:26-29`
```python
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-fmlk*=ob%&&$iv+bl()ifr-15(_j5)f(1!tnkts^y6co&#zw*f'
)
```

**Risk:** If the `.env` file fails to load or the `DJANGO_SECRET_KEY` env var is unset, Django falls back to a **publicly known `django-insecure-*` prefix key**. This is in git history. An attacker with the secret key can forge session cookies, CSRF tokens, and signed data — **full account takeover**.

**Fix:**
```python
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']  # No fallback — crash loud if missing
```
And generate a real production key on the server:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

### 2. DEBUG Defaults to True

**File:** `core/settings.py:34`
```python
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')
```

**Risk:** If `.env` is missing in production, `DEBUG=True` leaks stack traces, settings, database queries, and secret values on every error page.

**Fix:** Remove the default — if not set, crash:
```python
DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true', '1', 'yes')
```
Better: only allow `True` via explicit env var in dev.

---

### 3. Stripe Webhook Signature Bypassable

**File:** `main/views.py:190`
```python
endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
```

**Risk:** `STRIPE_WEBHOOK_SECRET` env var defaults to `''` (empty string). When empty, `stripe.Webhook.construct_event()` with an empty secret **silently skips signature verification**. Anyone who knows the webhook URL can forge payment-intent.succeeded events.

**Fix:**
```python
endpoint_secret = os.environ['STRIPE_WEBHOOK_SECRET']  # No fallback
```
Validate the secret is non-empty before calling construct_event:
```python
if not endpoint_secret:
    return HttpResponse(status=500)  # Misconfigured
```

---

### 4. No File Upload Validation (RCE Vector)

**Files:**
- `main/forms.py:33-40` — `BulkPhotoForm` uses generic `MultipleFileField` (not `ImageField`)
- `main/views.py:107-113` — No content-type or magic-byte checking before `Photo.objects.create(image=img)`

**Risk:** The form field uses `forms.FileField`, not `ImageField`. Django's `ImageField` validates that the file is a valid image via Pillow. Without it, an attacker can upload arbitrary files (`.exe`, `.php`, `.py`, `.html`) directly into the `media/` directory, which in DEBUG mode is served by Django's static file handler. **This is a remote code execution vector.**

**Fix:**
```python
# In BulkPhotoForm:
images = forms.ImageField(  # Use ImageField, not FileField
    widget=MultipleFileInput(),
    label='Photos'
)
```
Or add server-side validation:
```python
from PIL import Image
import io

for img in images:
    try:
        Image.open(io.BytesIO(img.read()))  # Verify it's a real image
        img.seek(0)
    except Exception:
        errors.append(f'{img.name}: invalid image file')
        continue
```

Additionally, validate video uploads in admin with magic bytes check.

---

### 5. Media Files Served by Django Dev Server in Production

**File:** `core/urls.py:22-23`
```python
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

**Risk:** This only runs in DEBUG mode, but the media directory is world-readable on disk. If DEBUG is ever accidentally True, every uploaded file (including ones that shouldn't be public) is directly served.

**Fix:** Ensure `DEBUG=False` in production (see #2). In production, configure your reverse proxy (Nginx/Caddy) to serve media files — never let Django handle them.

---

### 6. Stripe Secret Key in Views (Scope Issue)

**File:** `main/views.py:32`
```python
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', '«redacted:sk_test_…»')
```

**Risk:** `stripe.api_key` is set at **module import time** — it's a global. Any import of `main.views` sets it. If another view accidentally uses `stripe.*` API calls, it uses this key. The fallback `«redacted:sk_test_…»` string is also misleading — it's not a valid key, but the `# noqa` comment masks it.

**Fix:** Set the key once in `settings.py` or at application startup. Validate it's not a placeholder:
```python
# In settings.py:
STRIPE_SECRET_KEY = os.environ['STRIPE_SECRET_KEY']

# In views.py:
stripe.api_key = settings.STRIPE_SECRET_KEY
```

---

## 🟠 High Priority

### 7. Rate Limiting Not Effective Across Multiple Gunicorn Workers

**File:** `core/settings.py:115-119`
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

**Risk:** `LocMemCache` is per-process. With 4 gunicorn workers, an attacker can make `4 × 10 = 40` login attempts per hour. The rate limit check `E003` and `W001` are **silenced** in settings.

**Fix:** Use a shared cache backend:
```bash
pip install django-redis
```
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/1'),
    }
}
```
Remove the `SILENCED_SYSTEM_CHECKS` for rate limiting once Redis is configured.

---

### 8. Contact Form Data Lost (No Storage or Email)

**File:** `main/views.py:41-48`
```python
def home(request):
    if request.method == 'POST':
        name = request.POST.get('name', '')
        email = request.POST.get('email', '')
        message = request.POST.get('message', '')
        messages.success(...)
        return redirect('home')
```

**Risk:** Contact form submissions are accepted but **never stored or emailed**. The user thinks a message was sent, but it's silently discarded. No CSRF validation on this endpoint (it uses the template's `{% csrf_token %}` but the view itself doesn't validate the form).

**Fix:** Add a ContactMessage model and store submissions. Or integrate an email service:
```python
from django.core.mail import send_mail
send_mail(
    f'Contact: {name} <{email}>',
    message,
    settings.DEFAULT_FROM_EMAIL,
    [settings.CONTACT_EMAIL],
    fail_silently=False,
)
```

---

### 9. No Account Lockout (Only Rate Limiting)

**Risk:** The 10/hour rate limit is the only protection against brute-force login. An attacker can guess 10 passwords per hour, wait, and try again. No progressive delays, no account-level lockout.

**Fix:** Install and configure `django-axes`:
```bash
pip install django-axes
```
```python
INSTALLED_APPS = [
    ...
    'axes',
]
MIDDLEWARE.append('axes.middleware.AxesMiddleware')
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]
```

---

### 10. No Content Security Policy (CSP) Headers

**Risk:** The site loads Stripe.js from `https://js.stripe.com/v3/` — an inline script in `checkout.html` uses `Stripe('{{ stripe_key }}')`. Without CSP, XSS attacks can inject arbitrary scripts and exfiltrate the Stripe publishable key or redirect payment forms.

**Fix:** Add `django-csp`:
```bash
pip install django-csp
```
```python
MIDDLEWARE.append('csp.middleware.CSPMiddleware')

CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "https://js.stripe.com")
CSP_FRAME_SRC = ("https://js.stripe.com",)
CSP_CONNECT_SRC = ("'self'",)
CSP_IMG_SRC = ("'self'", "data:",)
```

---

### 11. No Referrer-Policy Header

**Risk:** Payment flow may leak the referring URL (including order IDs) to external resources.

**Fix:** Add in `settings.py`:
```python
SECURE_REFERRER_POLICY = 'same-origin'  # or 'strict-origin-when-cross-origin'
```

---

## 🟡 Medium Priority

### 12. HSTS Not Configured

**File:** `core/settings.py:194-196`
```python
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
```

**Fix:** After verifying HTTPS works:
```python
SECURE_HSTS_SECONDS = 31536000   # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

---

### 13. Deprecated `SECURE_BROWSER_XSS_FILTER` Setting

**File:** `core/settings.py:192`
```python
SECURE_BROWSER_XSS_FILTER = True
```

**Risk:** This setting was **removed in Django 5.0**. It has no effect — worse, it creates a false sense of security. The `X-XSS-Protection` header is deprecated in all modern browsers.

**Fix:** Remove the line. Replace with a proper CSP header (see #10).

---

### 14. Stripe PaymentIntent Without Idempotency Key

**File:** `main/views.py:151-160`
```python
intent = stripe.PaymentIntent.create(
    amount=TIER_PRICES[tier],
    currency='usd',
    ...
)
```

**Risk:** Without an idempotency key, a network retry could create duplicate PaymentIntents (and charges) for the same order. This is a **double-charge risk**.

**Fix:**
```python
import uuid
intent = stripe.PaymentIntent.create(
    amount=TIER_PRICES[tier],
    currency='usd',
    idempotency_key=f'order_{order.id}_{uuid.uuid4()}',
    ...
)
```

---

### 15. Database Passwords in Env Without Encryption at Rest

**Risk:** `DB_PASSWORD` is set in `.env` in plaintext. The SQLite database file `db.sqlite3` is not encrypted. If the server disk is compromised, all user credentials, session data, and order records are readable.

**Fix:**
- Never commit `.env` to git (already in `.gitignore` ✓, but verify `/.env` is not staged)
- Use encrypted volumes for the database
- For PostgreSQL: enable `ssl_mode=require` in DATABASE_URL
- Consider `django-encrypted-model-fields` for sensitive fields (user email, shipping address)

---

### 16. No Rate Limiting on Create-Order Endpoint

**File:** `main/views.py:131`
```python
@login_required
def create_order(request, tier):
```

**Risk:** An authenticated user can call `/order/digital/` repeatedly, creating unlimited unpaid Order objects and Stripe PaymentIntents. While Stripe intents don't auto-charge, this is a resource exhaustion vector (database bloat, Stripe API rate limit consumption).

**Fix:** Add rate limiting:
```python
@ratelimit(key='user', rate='5/h', method='POST', block=True)
@login_required
def create_order(request, tier):
```

---

### 17. Slideshow Generator — Potential Image Bomb / Resource Exhaustion

**File:** `main/utils/slideshow_generator.py:77`
```python
clip = ImageClip(str(photo.image.path), duration=3.5)
```

**Risk:** MoviePy/PIL opens user-uploaded images into memory. A crafted "image bomb" (e.g., a tiny JPEG that decompresses to gigabytes) can OOM the server. The 60MB upload limit helps but doesn't prevent decompression bombs.

**Fix:** Add Pillow validation before processing:
```python
from PIL import Image
MAX_IMAGE_PIXELS = 100_000_000  # 100 MP
img = Image.open(photo.image.path)
if img.width * img.height > MAX_IMAGE_PIXELS:
    raise ValueError(f"Image too large: {img.width}x{img.height}")
```

---

### 18. Admin `download_selected_as_zip` — Path Traversal / Enumeration

**File:** `main/admin.py:46`
```python
path = photo.image.path
arcname = f'{photo.user.username}/{photo.id:04d}_{photo.image.name.split("/")[-1]}'
```

**Risk:** If `photo.image.path` ever resolves outside the media directory (e.g., via a symlink or malicious path), the ZIP could include arbitrary files. Low risk for current code but a hardening opportunity.

**Fix:** Validate the resolved path is within MEDIA_ROOT:
```python
import pathlib
media_root = pathlib.Path(settings.MEDIA_ROOT).resolve()
photo_path = pathlib.Path(photo.image.path).resolve()
if not str(photo_path).startswith(str(media_root)):
    continue  # skip files outside media root
```

---

## 🟢 Low Priority / Informational

### 19. No SESSION_COOKIE_SAMESITE Setting

Django 5.2 defaults to `'Lax'`, which is appropriate, but explicit is better:
```python
SESSION_COOKIE_SAMESITE = 'Lax'
```

### 20. No Tests Written

**File:** `main/tests.py` contains only the default import. No tests for:
- Rate limiting behavior
- File upload validation
- Stripe webhook HMAC verification
- Payment flow rollback
- Session expiry

**Recommendation:** Write tests before production deployment.

---

## 📋 Production Deployment Checklist

| # | Item | Status |
|---|------|--------|
| 1 | Set `DJANGO_SECRET_KEY` to a real 64-byte `secrets.token_urlsafe()` key | ❌ |
| 2 | Set `DJANGO_DEBUG=False` | ❌ |
| 3 | Set `DJANGO_ALLOWED_HOSTS` to actual domain | ❌ |
| 4 | Set `STRIPE_SECRET_KEY` (live key) | ❌ |
| 5 | Set `STRIPE_WEBHOOK_SECRET` (live webhook signing secret) | ❌ |
| 6 | Set `DATABASE_URL` to PostgreSQL with SSL | ❌ |
| 7 | Set `REDIS_URL` for shared cache (rate limiting) | ❌ |
| 8 | Switch from LocMemCache to Redis/django-redis | ❌ |
| 9 | Configure Nginx/Caddy to serve `/media/` files | ❌ |
| 10 | Enable HTTPS with Let's Encrypt | ❌ |
| 11 | Set `SECURE_HSTS_SECONDS = 31536000` | ❌ |
| 12 | Add CSP headers via django-csp | ❌ |
| 13 | Add `django-axes` for account lockout | ❌ |
| 14 | Install `psycopg2-binary` or `psycopg` for PostgreSQL | ❌ |
| 15 | Set `CONN_MAX_AGE` for persistent DB connections | ❌ |
| 16 | Use `gunicorn` with `--workers=4` (or CPU×2+1) | ❌ |
| 17 | Systemd/tmux service for gunicorn process | ❌ |
| 18 | Regular database backups | ❌ |

---

## Summary of Required Dependency Changes

```diff
 requirements.txt
+django-csp>=3.0,<4.0
+django-axes>=6.0,<7.0
+django-redis>=5.0,<6.0
+psycopg2-binary>=2.9,<3.0
```

## Quick-Win Security Settings Block

Add this block to `core/settings.py`:

```python
# ── Production Security Hardening ──────────────────────────────
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = 'same-origin'
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_NAME = '__Host-sessionid'  # prefix for secure cookies

# Remove deprecated setting:
# SECURE_BROWSER_XSS_FILTER = True   # ← DELETE THIS LINE
```
