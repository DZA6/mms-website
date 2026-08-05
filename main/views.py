from pathlib import Path

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from .forms import BulkPhotoForm, BusinessMediaForm
from .models import Photo, Order, SlideShow, ContactMessage, Cart, CartItem, Video, BusinessProfile
from .email_helper import send_order_email


def robots_txt(request):
    """Simple robots.txt — allow all crawlers, point at the sitemap."""
    return HttpResponse(
        "User-agent: *\nAllow: /\n\nSitemap: https://www.memorialmediaservices.org/sitemap.xml\n",
        content_type="text/plain",
    )


def privacy_policy(request):
    """Privacy policy + cookie disclosure (CCPA/CPRA)."""
    return render(request, 'privacy.html')


def terms_and_conditions(request):
    """Terms & conditions page (shown at checkout with required agreement)."""
    return render(request, 'terms.html')


def sitemap_xml(request):
    """Minimal sitemap for the public pages."""
    domain = "https://www.memorialmediaservices.org"
    urls = ["", "pricing/", "login/", "signup/", "privacy/", "terms/"]
    entries = "".join(
        f"<url><loc>{domain}/{u}</loc><changefreq>weekly</changefreq></url>"
        for u in urls
    )
    return HttpResponse(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>\n',
        content_type="application/xml",
    )


import stripe

# Set Stripe API key from settings
stripe.api_key = settings.STRIPE_SECRET_KEY

TIER_PRICES = {
    'basic': 4999,
    'digital': 7499,
}


def home(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        service = request.POST.get('service', '').strip()
        message_text = request.POST.get('message', '').strip()

        # Validate required fields
        if not name or not email or not message_text:
            messages.error(request, 'Please fill in all required fields.')
            return redirect('home')

        # Store contact submission in database
        ContactMessage.objects.create(
            name=name,
            email=email,
            service=service,
            message=message_text,
        )

        messages.success(request, f'Thanks {name}! We\'ll get back to you within 2 hours.')
        return redirect('home')

    return render(request, 'index.html')


def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
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

    # Post-payment confirmation banner
    payment_success = request.GET.get('payment') == 'success'
    # Orders that still need the deceased's details (paid but no name yet)
    pending_details = orders.filter(status='paid', deceased_name='')

    return render(request, 'dashboard.html', {
        'photos': photos,
        'orders': orders,
        'slideshows': slideshows,
        'completed_slideshows': completed_slideshows,
        'MAX_PHOTOS': 50,
        'payment_success': payment_success,
        'pending_details': pending_details,
    })


MAX_PHOTOS = 50


@login_required
def upload_photo(request):
    """Upload up to 50 photos at once for a tribute slideshow."""
    photo_count = Photo.objects.filter(user=request.user).count()

    if request.method == 'POST':
        form = BulkPhotoForm(request.POST, request.FILES)
        if form.is_valid():
            title = form.cleaned_data['title']
            uploaded_files = request.FILES.getlist('images')

            # Enforce per-user photo limit
            if photo_count + len(uploaded_files) > MAX_PHOTOS:
                remaining = MAX_PHOTOS - photo_count
                messages.error(
                    request,
                    f'You can only upload {remaining} more photo(s) (limit is {MAX_PHOTOS}).'
                )
                return render(request, 'upload.html', {
                    'form': BulkPhotoForm(),
                    'photo_count': photo_count,
                    'MAX_PHOTOS': MAX_PHOTOS,
                })

            saved_count = 0
            for f in uploaded_files:
                # Validate it's an image
                if not f.content_type.startswith('image/'):
                    continue
                ext = Path(f.name).suffix.lower()
                if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                    continue

                Photo.objects.create(
                    user=request.user,
                    title=title,
                    image=f,
                )
                saved_count += 1

            if saved_count == 1:
                messages.success(request, 'Photo uploaded successfully!')
            elif saved_count > 1:
                messages.success(request, f'{saved_count} photos uploaded successfully!')
            else:
                messages.error(request, 'No valid image files were found. Please upload JPG, PNG, GIF, or WebP.')

            return redirect('dashboard')
    else:
        form = BulkPhotoForm()

    return render(request, 'upload.html', {
        'form': form,
        'photo_count': photo_count,
        'MAX_PHOTOS': MAX_PHOTOS,
    })


@login_required
def create_order(request, tier):
    if tier not in TIER_PRICES:
        messages.error(request, 'Invalid tier selected.')
        return redirect('pricing')

    if request.method == 'POST':
        order = Order.objects.create(
            user=request.user,
            tier=tier,
            status='pending',
            notes=request.POST.get('notes', ''),
            # Funeral details
            deceased_name=request.POST.get('deceased_name', ''),
            date_of_birth=request.POST.get('date_of_birth') or None,
            date_of_death=request.POST.get('date_of_death') or None,
            service_type=request.POST.get('service_type', ''),
            service_date=request.POST.get('service_date') or None,
            service_time=request.POST.get('service_time', ''),
            service_location=request.POST.get('service_location', ''),
            burial_place=request.POST.get('burial_place', ''),
            preferred_song=request.POST.get('preferred_song', ''),
            special_notes=request.POST.get('special_notes', ''),
        )

        try:
            # Create a Stripe Checkout Session
            checkout_session = stripe.checkout.Session.create(
                mode='payment',
                managed_payments={'enabled': False},
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': order.get_tier_display(),
                            'description': 'Custom HD tribute slideshow with music + memorial flyer PDF',
                        },
                        'unit_amount': TIER_PRICES[tier],
                    },
                    'quantity': 1,
                }],
                metadata={
                    'order_id': order.id,
                    'user_id': request.user.id,
                    'tier': tier,
                },
                success_url=request.build_absolute_uri(f'/order/{order.id}/success/'),
                cancel_url=request.build_absolute_uri('/dashboard/'),
                customer_email=request.user.email,
            )

            order.stripe_payment_intent = checkout_session.payment_intent or ''
            order.save()

            # Redirect directly to Stripe Checkout
            return redirect(checkout_session.url, code=303)

        except Exception as e:
            order.delete()
            messages.error(request, f'Payment system error: {str(e)}')
            return redirect('dashboard')

    tier_names = {'basic': 'Basic Tribute', 'digital': 'Tribute Package', 'print': 'Tribute Print', 'complete': 'Complete Tribute'}
    return render(request, 'order_form.html', {
        'tier': tier,
        'tier_name': tier_names.get(tier, tier),
        'price': f'${TIER_PRICES[tier] / 100:.2f}',
        'service_type_options': SERVICE_TYPE_OPTIONS,
    })


@csrf_exempt
def stripe_webhook(request):
    """Handle Stripe webhook events with signature verification."""
    import logging
    logger = logging.getLogger(__name__)
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    # Validate webhook secret is configured
    if not endpoint_secret:
        return HttpResponse('Webhook secret not configured', status=500)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return HttpResponse('Invalid payload', status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse('Invalid signature', status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        order_id = metadata.get('order_id')
        cart_id = metadata.get('cart_id')

        # Single order checkout (direct package purchase from old flow)
        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                order.status = 'paid'
                order.stripe_payment_intent = session.get('payment_intent', '')
                order.save()

                # Send automated thank-you email
                success, msg = send_order_email(order)
                if not success:
                    logger.error(f'Failed to send order email for order #{order.id}: {msg}')

                # Notify the owner of the new order (independent of Hermes availability)
                try:
                    from .email_helper import send_new_order_notification
                    owner_success, owner_msg = send_new_order_notification(order)
                    if not owner_success:
                        logger.error(f'Failed to send owner notification for order #{order.id}: {owner_msg}')
                except Exception as e:
                    logger.error(f'Owner notification error for order #{order.id}: {e}')

                if order.tier in ('basic', 'digital', 'complete'):
                    slideshow = SlideShow.objects.create(
                        user=order.user,
                        order=order,
                        title=f'Tribute for Order #{order.id}',
                        status='pending',
                    )
                    # Link all user's photos to this slideshow
                    slideshow.photos.set(Photo.objects.filter(user=order.user))
            except Order.DoesNotExist:
                pass

        # Multi-item cart checkout — mark only the orders created for THIS session
        if cart_id:
            user_id = metadata.get('user_id')
            order_ids = metadata.get('order_ids', '')
            if user_id:
                pending_orders = Order.objects.filter(
                    user__id=user_id,
                    status='pending'
                )
                # Prefer the explicit order ids from checkout metadata; fall back
                # to nothing (never sweep ALL pending orders — abandoned orders
                # from the old create_order flow must not be charged)
                if order_ids:
                    ids = [i for i in order_ids.split(',') if i.isdigit()]
                    pending_orders = pending_orders.filter(id__in=ids)
                else:
                    pending_orders = pending_orders.none()
                for idx, order in enumerate(pending_orders):
                    order.status = 'paid'
                    order.stripe_payment_intent = session.get('payment_intent', '')
                    order.save()

                    # Send email for the first order only
                    if idx == 0:
                        success, msg = send_order_email(order)
                        # Notify the owner of the new order (cart checkout)
                        try:
                            from .email_helper import send_new_order_notification
                            owner_success, owner_msg = send_new_order_notification(order)
                            if not owner_success:
                                logger.error(f'Failed to send owner notification for order #{order.id}: {owner_msg}')
                        except Exception as e:
                            logger.error(f'Owner notification error for order #{order.id}: {e}')

                    if order.tier in ('basic', 'digital', 'complete'):
                        slideshow = SlideShow.objects.create(
                            user=order.user,
                            order=order,
                            title=f'Tribute for Order #{order.id}',
                            status='pending',
                        )
                        slideshow.photos.set(Photo.objects.filter(user=order.user))

    return HttpResponse(status=200)


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    slideshows = SlideShow.objects.filter(order=order)
    return render(request, 'order_detail.html', {
        'order': order,
        'slideshows': slideshows,
    })


@login_required
def order_details(request, order_id):
    """Collect the deceased's details for a paid order (post-payment intake)."""
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if request.method == 'POST':
        order.deceased_name = request.POST.get('deceased_name', order.deceased_name)
        order.date_of_birth = request.POST.get('date_of_birth') or order.date_of_birth
        order.date_of_death = request.POST.get('date_of_death') or order.date_of_death
        order.service_type = request.POST.get('service_type', order.service_type)
        order.service_date = request.POST.get('service_date') or order.service_date
        order.service_time = request.POST.get('service_time', order.service_time)
        order.service_location = request.POST.get('service_location', order.service_location)
        order.burial_place = request.POST.get('burial_place', order.burial_place)
        order.preferred_song = request.POST.get('preferred_song', order.preferred_song)
        order.special_notes = request.POST.get('special_notes', order.special_notes)
        order.save()
        messages.success(request, 'Tribute details saved. You can upload photos next.')
        return redirect('dashboard')

    tier_names = {'basic': 'Basic Tribute', 'digital': 'Tribute Package', 'print': 'Tribute Print', 'complete': 'Complete Tribute'}
    return render(request, 'order_form.html', {
        'order': order,
        'tier': order.tier,
        'tier_name': tier_names.get(order.tier, order.get_tier_display()),
        'price': f'${TIER_PRICES.get(order.tier, 0) / 100:.2f}',
        'editing': True,
        'service_type_options': SERVICE_TYPE_OPTIONS,
    })


SERVICE_TYPE_OPTIONS = [
    'Funeral Service',
    'Memorial Service',
    'Celebration of Life',
    'Graveside Service',
    'Viewing / Visitation',
    'Other',
]


@login_required
def order_success(request, order_id):
    """Thank-you page shown after successful Stripe Checkout redirect."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    amount = TIER_PRICES.get(order.tier, 0) / 100
    return render(request, 'order_success.html', {
        'order': order,
        'amount': amount,
    })


def pricing_page(request):
    return render(request, 'pricing.html')


@login_required
def download_slideshow_file(request, slideshow_id, file_type):
    """Serve a slideshow file with auth check — user must own it."""
    slideshow = get_object_or_404(SlideShow, id=slideshow_id, user=request.user)

    if file_type == 'video':
        if not slideshow.video_file:
            messages.error(request, 'Video file not available yet.')
            return redirect('dashboard')
        file_path = slideshow.video_file.path
        file_name = f'tribute_{slideshow.order_id}.mp4'
        content_type = 'video/mp4'
    elif file_type == 'pdf':
        if not slideshow.pdf_file:
            messages.error(request, 'PDF file not available yet.')
            return redirect('dashboard')
        file_path = slideshow.pdf_file.path
        file_name = f'flyer_{slideshow.order_id}.pdf'
        content_type = 'application/pdf'
    else:
        messages.error(request, 'Invalid file type.')
        return redirect('dashboard')

    import mimetypes
    content_type, _ = mimetypes.guess_type(file_name)
    if not content_type:
        content_type = 'application/octet-stream'

    response = HttpResponse(open(file_path, 'rb').read(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{file_name}"'
    return response


def get_or_create_cart(request):
    """Get the user's active cart or create one."""
    cart, _ = Cart.objects.get_or_create(user=request.user)
    return cart


@login_required
def add_to_cart(request, tier):
    """Add a tier to the user's cart."""
    if tier not in TIER_PRICES:
        messages.error(request, 'Invalid package selected.')
        return redirect('pricing')

    cart = get_or_create_cart(request)
    existing = cart.items.filter(tier=tier).first()
    if existing:
        existing.quantity += 1
        existing.save()
    else:
        CartItem.objects.create(cart=cart, tier=tier)

    messages.success(request, f'Added to cart!')
    return redirect('view_cart')


@login_required
def view_cart(request):
    """Display the user's cart."""
    cart = get_or_create_cart(request)
    items = cart.items.all()
    return render(request, 'cart.html', {
        'cart': cart,
        'items': items,
        'total': cart.total_cents(),
        'stripe_key': settings.STRIPE_PUBLISHABLE_KEY,
    })


@login_required
def remove_from_cart(request, item_id):
    """Remove an item from the cart."""
    cart = get_or_create_cart(request)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    item.delete()
    messages.success(request, 'Item removed from cart.')
    return redirect('view_cart')


@login_required
def checkout_cart(request):
    """Checkout — creates orders + Stripe Checkout Session for all cart items."""
    cart = get_or_create_cart(request)
    items = cart.items.all()

    if not items:
        messages.error(request, 'Your cart is empty.')
        return redirect('pricing')

    if request.method == 'POST':
        # Terms agreement is a hard requirement — enforce server-side too
        # (the HTML `required` attribute only stops well-behaved browsers).
        if not request.POST.get('agree_terms'):
            messages.error(
                request,
                'Please read and accept the Terms & Conditions and Privacy Policy '
                'before checking out.',
            )
            return redirect('view_cart')

        # Create a single Stripe Checkout Session with line items for each cart item
        line_items = []
        orders = []
        for item in items:
            for _ in range(item.quantity):
                order = Order.objects.create(
                    user=request.user,
                    tier=item.tier,
                    status='pending',
                )
                orders.append(order)
                line_items.append({
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': item.tier_display(),
                        },
                        'unit_amount': item.tier_price_cents(),
                    },
                    'quantity': 1,
                })

        try:
            # Record order ids in session metadata so the webhook marks ONLY
            # these orders paid (never abandoned pending orders from other flows)
            order_ids = ','.join(str(o.id) for o in orders)
            checkout_session = stripe.checkout.Session.create(
                mode='payment',
                managed_payments={'enabled': False},
                line_items=line_items,
                metadata={
                    'cart_id': cart.id,
                    'user_id': request.user.id,
                    'order_ids': order_ids,
                },
                success_url=request.build_absolute_uri('/dashboard/?payment=success'),
                cancel_url=request.build_absolute_uri('/cart/'),
                customer_email=request.user.email,
            )

            # Save the payment intent and clear the cart
            for order in orders:
                order.stripe_payment_intent = checkout_session.payment_intent or ''
                order.save()

            cart.items.all().delete()

            return redirect(checkout_session.url, code=303)

        except Exception as e:
            for order in orders:
                order.delete()
            messages.error(request, f'Payment error: {str(e)}')
            return redirect('view_cart')

    return render(request, 'cart.html', {
        'cart': cart,
        'items': items,
        'total': cart.total_cents(),
        'stripe_key': settings.STRIPE_PUBLISHABLE_KEY,
    })


# =====================================================================
# BUSINESS PORTAL — partner businesses (funeral homes, photographers)
# upload/download media on behalf of customers.
# =====================================================================

def _get_business(user):
    """Return the user's approved BusinessProfile, or None."""
    if not user.is_authenticated:
        return None
    try:
        bp = user.business_profile
        return bp if bp.is_approved else None
    except BusinessProfile.DoesNotExist:
        return None


def business_portal(request):
    """Landing page for the business portal — public, explains access."""
    bp = _get_business(request.user) if request.user.is_authenticated else None
    return render(request, 'business/portal.html', {'business': bp})


@login_required
def business_dashboard(request):
    """Partner dashboard: list assigned orders, upload media, download."""
    bp = _get_business(request.user)
    if not bp:
        messages.error(request, "Your business account isn't approved yet. Contact us.")
        return redirect('business_portal')

    orders = Order.objects.filter(assigned_business=bp).order_by('-created_at')

    # Build the per-order media form (limit to this business's orders)
    form = BusinessMediaForm(auto_id=False)
    form.fields['order'].queryset = orders

    if request.method == 'POST':
        form = BusinessMediaForm(request.POST, request.FILES)
        form.fields['order'].queryset = orders
        if form.is_valid():
            order = form.cleaned_data['order']
            photo_title = form.cleaned_data.get('photo_title') or f"Photos for order #{order.id}"
            video_title = form.cleaned_data.get('video_title') or f"Videos for order #{order.id}"
            saved_photos = 0
            saved_videos = 0

            # Photos
            for f in form.cleaned_data.get('images') or []:
                Photo.objects.create(
                    user=order.user, order=order, business=bp,
                    title=photo_title, image=f,
                )
                saved_photos += 1

            # Videos
            for f in form.cleaned_data.get('videos') or []:
                Video.objects.create(
                    user=order.user, order=order, business=bp,
                    title=video_title, video_file=f,
                )
                saved_videos += 1

            if saved_photos or saved_videos:
                messages.success(
                    request,
                    f"Uploaded {saved_photos} photo(s) and {saved_videos} video(s) to order #{order.id}."
                )
                send_business_upload_notice(order, bp, saved_photos, saved_videos)
            return redirect('business_dashboard')

    # Per-order media counts for the dashboard table
    order_stats = []
    for o in orders:
        order_stats.append({
            'order': o,
            'photo_count': o.photos.count(),
            'video_count': o.videos.count(),
        })

    return render(request, 'business/dashboard.html', {
        'business': bp,
        'order_stats': order_stats,
        'form': form,
    })


def send_business_upload_notice(order, business, n_photos, n_videos):
    """Email the owner when a partner uploads media to an order."""
    try:
        from .email_helper import send_simple_email
        subject = f"📸 Partner upload: order #{order.id}"
        body = (
            f"{business.business_name} uploaded {n_photos} photo(s) and "
            f"{n_videos} video(s) to order #{order.id} "
            f"(customer: {order.user.username}, tier: {order.get_tier_display()})."
        )
        send_simple_email(settings.OWNER_EMAIL, subject, body)
    except Exception:
        pass  # non-blocking; the upload itself already succeeded


@login_required
def business_download_order(request, order_id):
    """Download all photos + videos for an order as a ZIP."""
    bp = _get_business(request.user)
    if not bp:
        messages.error(request, "Business access required.")
        return redirect('business_portal')

    order = get_object_or_404(Order, id=order_id, assigned_business=bp)

    import io
    import zipfile

    buffer = io.BytesIO()
    safe_name = "".join(c for c in f"order_{order.id}" if c.isalnum() or c in "._-")
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, ph in enumerate(order.photos.all(), 1):
            if ph.image:
                try:
                    zf.write(ph.image.path, arcname=f"photos/{i:02d}_{Path(ph.image.name).name}")
                except FileNotFoundError:
                    continue
        for i, v in enumerate(order.videos.all(), 1):
            if v.video_file:
                try:
                    zf.write(v.video_file.path, arcname=f"videos/{i:02d}_{Path(v.video_file.name).name}")
                except FileNotFoundError:
                    continue

    buffer.seek(0)
    resp = HttpResponse(buffer.getvalue(), content_type='application/zip')
    resp['Content-Disposition'] = f'attachment; filename="{safe_name}_media.zip"'
    return resp
