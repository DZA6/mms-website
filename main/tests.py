from django.test import TestCase

from .models import Order
from .views import TIER_PRICES


class TierConfigurationTests(TestCase):
    def test_all_priced_tiers_are_valid_order_choices(self):
        valid_prices = set(TIER_PRICES)
        valid_choices = set(dict(Order.TIER_CHOICES))

        self.assertSetEqual(valid_prices, valid_choices)
