from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                            'LOCATION': 'auth-throttle-tests'}}

# The suite itself runs with very high limits (settings.TESTING), so these tests
# set their own. DRF reads the rates once at import, hence patch.dict.
LOW_RATES = {
    'auth_login': '4/min',
    'auth_login_account': '2/min',
    'auth_register': '2/min',
    'auth_token': '2/min',
    'dj_rest_auth': '2/min',
}


@override_settings(CACHES=LOCMEM_CACHE)
class AuthThrottleTests(TestCase):

    def setUp(self):
        cache.clear()
        patcher = patch.dict(ScopedRateThrottle.THROTTLE_RATES, LOW_RATES)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = APIClient()

    def _post_login(self, username, **extra):
        return self.client.post('/api/auth/token/', {'username': username, 'password': 'wrong'},
                                format='json', **extra)

    def test_repeated_guesses_at_one_account_get_429(self):
        self.assertEqual(self._post_login('victim').status_code, 401)
        self.assertEqual(self._post_login('victim').status_code, 401)
        self.assertEqual(self._post_login('victim').status_code, 429)

    def test_the_account_limit_ignores_the_caller_and_username_case(self):
        self._post_login('victim', REMOTE_ADDR='10.0.0.1')
        self._post_login('VICTIM ', REMOTE_ADDR='10.0.0.2')
        self.assertEqual(self._post_login('victim', REMOTE_ADDR='10.0.0.3').status_code, 429)

    def test_one_user_being_limited_leaves_others_able_to_log_in(self):
        """Every www login reaches Django from the web server's own address, so a
        purely per-address limit at this strength would be site-wide."""
        self._post_login('victim')
        self._post_login('victim')
        self.assertEqual(self._post_login('victim').status_code, 429)
        self.assertEqual(self._post_login('someone-else').status_code, 401)

    def test_spraying_many_accounts_from_one_address_hits_the_address_limit(self):
        for number in range(4):
            self.assertEqual(self._post_login(f'user{number}').status_code, 401)
        self.assertEqual(self._post_login('user-next').status_code, 429)

    def test_the_address_comes_from_the_last_proxy_hop_not_the_clients_claim(self):
        """Caddy is the one proxy, so a forged X-Forwarded-For prefix must not
        give each request a fresh bucket."""
        for number in range(4):
            self._post_login(f'user{number}',
                             HTTP_X_FORWARDED_FOR=f'1.2.3.{number}, 203.0.113.9')
        response = self._post_login('user-next', HTTP_X_FORWARDED_FOR='9.9.9.9, 203.0.113.9')
        self.assertEqual(response.status_code, 429)
        other = self._post_login('user-next', HTTP_X_FORWARDED_FOR='9.9.9.9, 203.0.113.10')
        self.assertEqual(other.status_code, 401)

    def test_register_gets_429(self):
        for _ in range(2):
            self.assertEqual(
                self.client.post('/api/auth/register/', {}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/auth/register/', {}, format='json').status_code, 429)

    def test_token_refresh_and_verify_get_429(self):
        for url in ('/api/auth/token/refresh/', '/api/auth/token/verify/'):
            with self.subTest(url=url):
                cache.clear()
                for _ in range(2):
                    self.client.post(url, {}, format='json')
                self.assertEqual(self.client.post(url, {}, format='json').status_code, 429)

    def test_dj_rest_auth_login_and_password_reset_get_429(self):
        for url in ('/api/auth/login/', '/api/auth/password/reset/', '/api/auth/registration/'):
            with self.subTest(url=url):
                cache.clear()
                for _ in range(2):
                    self.client.post(url, {}, format='json')
                self.assertEqual(self.client.post(url, {}, format='json').status_code, 429)

    def test_a_malformed_login_body_is_not_a_server_error(self):
        response = self.client.post('/api/auth/token/', ['not', 'a', 'mapping'], format='json')
        self.assertLess(response.status_code, 500)

    def test_other_endpoints_are_not_throttled(self):
        for _ in range(5):
            self.assertNotEqual(self.client.get('/api/avatar-presets/').status_code, 429)


class ThrottleConfigTests(TestCase):

    def test_every_scope_has_a_valid_rate(self):
        throttle = ScopedRateThrottle()
        for scope, rate in settings.AUTH_THROTTLE_RATES.items():
            with self.subTest(scope=scope):
                self.assertGreater(throttle.parse_rate(rate)[0], 0)
        self.assertEqual(set(settings.AUTH_THROTTLE_RATES), set(LOW_RATES))
