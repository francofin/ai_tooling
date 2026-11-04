"""Rate limits for login endpoints. Scopes and rates are in settings."""
import hashlib
import math
from collections.abc import Mapping
from functools import wraps

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)


def _username_ident(username):
    """A stable, non-reversible bucket name, or None when no username was sent."""
    if not isinstance(username, str) or not username.strip():
        return None
    return hashlib.sha256(username.strip().lower().encode('utf-8')).hexdigest()


class LoginAccountThrottle(SimpleRateThrottle):
    """Limits guesses per submitted username, whatever address they come from.

    The address-based limit cannot do this job: `www` logins all reach Django
    from the web server's address, so at this strength it would lock out the
    whole site.
    """
    scope = 'auth_login_account'

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, Mapping) else {}
        ident = _username_ident(data.get(get_user_model().USERNAME_FIELD))
        if ident is None:
            return None
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


class FormLoginAddressThrottle(SimpleRateThrottle):
    scope = 'form_login'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class FormLoginAccountThrottle(SimpleRateThrottle):
    scope = 'form_login_account'

    def get_cache_key(self, request, view):
        ident = _username_ident(request.POST.get('username'))
        if ident is None:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': ident}


def limit_form_login(view):
    """Limits POSTs to an HTML password form, which DRF throttling cannot reach.

    The address is checked first so that a blocked address stops spending the
    account's budget, and cannot keep the owner locked out from elsewhere.
    """
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.method == 'POST':
            for throttle in (FormLoginAddressThrottle(), FormLoginAccountThrottle()):
                if not throttle.allow_request(request, None):
                    response = HttpResponse('Too many login attempts. Try again later.',
                                            status=429, content_type='text/plain')
                    response['Retry-After'] = str(math.ceil(throttle.wait()))
                    return response
        return view(request, *args, **kwargs)
    return wrapped
