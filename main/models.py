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
        ('basic', 'Basic Tribute — $49.99'),
        ('digital', 'Tribute Package — $89.99'),
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

    # Funeral details
    deceased_name = models.CharField(max_length=200, blank=True, verbose_name="Deceased's Full Name")
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Date of Birth")
    date_of_death = models.DateField(null=True, blank=True, verbose_name="Date of Passing")
    service_type = models.CharField(max_length=100, blank=True, verbose_name="Type of Service",
        help_text="e.g. Funeral Service, Memorial Service, Celebration of Life")
    service_date = models.DateField(null=True, blank=True, verbose_name="Date of Service")
    service_time = models.CharField(max_length=50, blank=True, verbose_name="Time of Service",
        help_text="e.g. 11:00 AM")
    service_location = models.CharField(max_length=300, blank=True, verbose_name="Service Location",
        help_text="Church, funeral home, or venue name and address")
    burial_place = models.CharField(max_length=300, blank=True, verbose_name="Burial / Interment Location")
    preferred_song = models.CharField(max_length=200, blank=True, verbose_name="Preferred Music/Song")
    special_notes = models.TextField(blank=True, verbose_name="Additional Notes",
        help_text="Any other details you'd like us to know")

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


class ContactMessage(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField()
    service = models.CharField(max_length=100, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Contact from {self.name}"

    class Meta:
        verbose_name = "Contact Message"
        verbose_name_plural = "Contact Messages"
        ordering = ["-created_at"]


class Cart(models.Model):
    """A shopping cart tied to a user session."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='carts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def total_cents(self):
        return sum(item.total_cents() for item in self.items.all())

    def total_dollars(self):
        return self.total_cents() / 100

    def total_display(self):
        return f'${self.total_cents() / 100:.0f}'

    def item_count(self):
        return self.items.count()

    def __str__(self):
        return f"Cart #{self.id} — {self.user.username} ({self.item_count()} items)"


class CartItem(models.Model):
    """An individual item in a shopping cart."""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    tier = models.CharField(max_length=20)  # 'basic' or 'digital'
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def tier_price_cents(self):
        from main.views import TIER_PRICES
        return TIER_PRICES.get(self.tier, 0)

    def total_cents(self):
        return self.tier_price_cents() * self.quantity

    def price_dollars(self):
        return self.tier_price_cents() / 100

    def total_dollars(self):
        return self.total_cents() / 100

    def tier_display(self):
        choices = dict(Order.TIER_CHOICES)
        return choices.get(self.tier, self.tier)

    def __str__(self):
        return f"{self.tier_display()} x{self.quantity}"
