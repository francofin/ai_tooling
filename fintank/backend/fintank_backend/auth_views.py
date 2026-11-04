"""simplejwt views with rate limits. Scopes and rates are in settings."""
import hashlib
from collections.abc import Mapping

from django.contrib.auth import get_user_model
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)


class LoginAccountThrottle(SimpleRateThrottle):
    """Limits guesses per submitted username, whatever address they come from.

    The address-based limit cannot do this job: `www` logins all reach Django
    from the web server's address, so at this strength it would lock out the
    whole site.
    """
    scope = 'auth_login_account'

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, Mapping) else {}
        username = data.get(get_user_model().USERNAME_FIELD)
        if not isinstance(username, str) or not username.strip():
            return None
        ident = hashlib.sha256(username.strip().lower().encode('utf-8')).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_scope = 'auth_login'
    throttle_classes = [LoginAccountThrottle, ScopedRateThrottle]


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_scope = 'auth_token'
    throttle_classes = [ScopedRateThrottle]


class ThrottledTokenVerifyView(TokenVerifyView):
    throttle_scope = 'auth_token'
    throttle_classes = [ScopedRateThrottle]
