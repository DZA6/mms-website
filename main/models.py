from django.db import models
from django.contrib.auth.models import User

class Photo(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    image = models.ImageField(upload_to='client_slideshows/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Order(models.Model):
    TIER_CHOICES = [
        ('digital', 'Tribute Package — $149'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid — Processing'),
        ('processing', 'In Production'),
        ('completed', 'Completed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stripe_payment_intent = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    # Shipping address (for print orders)
    shipping_name = models.CharField(max_length=200, blank=True)
    shipping_address = models.TextField(blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField(max_length=100, blank=True)
    shipping_zip = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"Order {self.id} — {self.user.username} — {self.get_tier_display()}"


class SlideShow(models.Model):
    """A generated video slideshow from a user's photos."""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('generating', 'Generating'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    video_file = models.FileField(upload_to='slideshows/', blank=True, null=True)
    pdf_file = models.FileField(upload_to='slideshows/', blank=True, null=True, verbose_name='Funeral Flyer PDF')
    photos = models.ManyToManyField(Photo, blank=True)
    music_choice = models.CharField(max_length=100, blank=True, default='gentle-piano')
    created_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f"Slideshow: {self.title} ({self.status})"
