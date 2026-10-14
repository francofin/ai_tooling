"""The billing fields exist, default to 'no subscription', and cannot be
written through the profile API -- only the webhook sets them."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import UserProfile

User = get_user_model()

BILLING_FIELDS = {
    'stripe_customer_id': 'cus_hacked',
    'stripe_subscription_id': 'sub_hacked',
    'subscription_status': 'active',
    'subscription_interval': 'year',
    'current_period_end': '2099-01-01T00:00:00Z',
    'cancel_at_period_end': True,
    'subscription_tier': 'pro',
}


def make_user(email='billing@example.com'):
    user = User.objects.create_user(username=email, email=email, password='sw0rdfish!x',
                                    first_name='Test', last_name='User')
    UserProfile.objects.get_or_create(user=user)
    return user


class ProfileBillingFieldTests(TestCase):

    def test_a_new_profile_has_no_subscription(self):
        profile = make_user().userprofile
        self.assertIsNone(profile.stripe_customer_id)
        self.assertIsNone(profile.stripe_subscription_id)
        self.assertIsNone(profile.subscription_status)
        self.assertIsNone(profile.subscription_interval)
        self.assertIsNone(profile.current_period_end)
        self.assertFalse(profile.cancel_at_period_end)

    def test_billing_fields_cannot_be_patched_through_the_profile_api(self):
        user = make_user()
        client = APIClient()
        client.force_authenticate(user)

        response = client.patch('/api/users/me/profile/update/', BILLING_FIELDS, format='json')

        self.assertLess(response.status_code, 500)
        profile = UserProfile.objects.get(user=user)
        self.assertIsNone(profile.stripe_customer_id)
        self.assertIsNone(profile.stripe_subscription_id)
        self.assertIsNone(profile.subscription_status)
        self.assertIsNone(profile.subscription_interval)
        self.assertIsNone(profile.current_period_end)
        self.assertFalse(profile.cancel_at_period_end)
        self.assertEqual(profile.subscription_tier, 'free')
