import json
import os
from pathlib import Path

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from django_ratelimit.decorators import ratelimit
from django_ratelimit import UNSAFE

from .forms import PhotoForm, BulkPhotoForm
from .models import Photo, Order, SlideShow

import stripe

# Load Stripe keys from environment or .env file
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(settings.BASE_DIR, '.env'))
except ImportError:
    pass

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_placeholder')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', 'pk_test_placeholder')

# Tier pricing
TIER_PRICES = {
    'digital': 14900,  # $149 in cents
}


def home(request):
    if request.method == 'POST':
        name = request.POST.get('name', '')
        email = request.POST.get('email', '')
        message = request.POST.get('message', '')
        messages.success(request, f'Thanks {name}! We\'ll get back to you within 2 hours.')
        return redirect('home')
    return render(request, 'index.html')


@ratelimit(key='ip', rate='10/h', method=UNSAFE, block=True)
def custom_login(request):
    """Rate-limited login view."""
    return LoginView.as_view(template_name='login.html')(request)


@ratelimit(key='ip', rate='10/h', method=UNSAFE, block=True)
def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'signup.html', {'form': form})


@login_required
def dashboard(request):
    photos = Photo.objects.filter(user=request.user).order_by('-uploaded_at')
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    slideshows = SlideShow.objects.filter(user=request.user).order_by('-created_at')
    completed_slideshows = slideshows.filter(status='completed')
    return render(request, 'dashboard.html', {
        'photos': photos,
        'orders': orders,
        'slideshows': slideshows,
        'completed_slideshows': completed_slideshows,
    })


@login_required
def upload_photo(request):
    MAX_PHOTOS = 60
    photo_count = Photo.objects.filter(user=request.user).count()

    if request.method == 'POST':
        form = BulkPhotoForm(request.POST, request.FILES)
        if form.is_valid():
            title = form.cleaned_data['title']
            images = request.FILES.getlist('images')

            # Check total won't exceed limit
            if photo_count + len(images) > MAX_PHOTOS:
                slots_left = MAX_PHOTOS - photo_count
                messages.error(
                    request,
                    f'You can only upload {slots_left} more photo(s) (max {MAX_PHOTOS}). '
                    f'You selected {len(images)}.'
                )
                return redirect('upload')

            created = 0
            errors = []
            for img in images:
                try:
                    Photo.objects.create(
                        user=request.user,
                        title=title,
                        image=img,
                    )
                    created += 1
                except Exception as e:
                    errors.append(f'{img.name}: {str(e)}')

            if created:
                messages.success(request, f'{created} photo(s) uploaded successfully! ({photo_count + created}/{MAX_PHOTOS})')
            if errors:
                messages.error(request, 'Some files failed: ' + '; '.join(errors))

            return redirect('dashboard')
    else:
        form = BulkPhotoForm()

    return render(request, 'upload.html', {'form': form, 'photo_count': photo_count, 'MAX_PHOTOS': MAX_PHOTOS})


@login_required
def create_order(request, tier):
    """Start a new order for the specified tier."""
    if tier not in TIER_PRICES:
        messages.error(request, 'Invalid tier selected.')
        return redirect('pricing')

    if request.method == 'POST':
        order = Order.objects.create(
            user=request.user,
            tier=tier,
            status='pending',
            shipping_name=request.POST.get('shipping_name', ''),
            shipping_address=request.POST.get('shipping_address', ''),
            shipping_city=request.POST.get('shipping_city', ''),
            shipping_state=request.POST.get('shipping_state', ''),
            shipping_zip=request.POST.get('shipping_zip', ''),
            notes=request.POST.get('notes', ''),
        )

        # Create payment intent
        try:
            intent = stripe.PaymentIntent.create(
                amount=TIER_PRICES[tier],
                currency='usd',
                metadata={
                    'order_id': order.id,
                    'user_id': request.user.id,
                    'tier': tier,
                },
            )
            order.stripe_payment_intent = intent.id
            order.save()

            return render(request, 'checkout.html', {
                'order': order,
                'client_secret': intent.client_secret,
                'stripe_key': STRIPE_PUBLISHABLE_KEY,
                'tier_name': order.get_tier_display(),
                'amount': TIER_PRICES[tier],
            })
        except Exception as e:
            order.delete()
            messages.error(request, f'Payment system error: {str(e)}')
            return redirect('dashboard')

    # GET — show order form
    tier_names = {'digital': 'Tribute Package'}
    return render(request, 'order_form.html', {
        'tier': tier,
        'tier_name': tier_names.get(tier, tier),
        'price': f'${TIER_PRICES[tier] // 100}',
    })


@csrf_exempt
def stripe_webhook(request):
    """Handle Stripe webhook events (payment success, etc.)."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    if event['type'] == 'payment_intent.succeeded':
        intent = event['data']['object']
        order_id = intent['metadata'].get('order_id')
        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                order.status = 'paid'
                order.save()

                # Create slideshow if tier includes digital
                if order.tier in ('digital', 'complete'):
                    photos = Photo.objects.filter(user=order.user)
                    SlideShow.objects.create(
                        user=order.user,
                        order=order,
                        title=f'Tribute for Order #{order.id}',
                        status='pending',
                    )
            except Order.DoesNotExist:
                pass

    return HttpResponse(status=200)


@login_required
def order_detail(request, order_id):
    """View details of an order."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    slideshows = SlideShow.objects.filter(order=order)
    return render(request, 'order_detail.html', {
        'order': order,
        'slideshows': slideshows,
    })


def pricing_page(request):
    """Standalone pricing page."""
    return render(request, 'pricing.html')
