"""Rate limits for login endpoints. Scopes and rates are in settings."""
import hashlib
import math
import unicodedata
from collections.abc import Mapping
from functools import wraps

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from dj_rest_auth.views import LoginView
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
    # NFKC first: Django's login form applies it, so other spellings log in as
    # the same user and must not get a budget of their own.
    normalized = unicodedata.normalize('NFKC', username).strip().lower()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


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


class RestAuthLoginAccountThrottle(LoginAccountThrottle):
    """The same budget as LoginAccountThrottle, for a view that also takes email.

    It reads email first, as dj_rest_auth's login does, so that sending a second
    field cannot buy a fresh bucket.
    """

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, Mapping) else {}
        ident = _username_ident(data.get('email') or data.get('username'))
        if ident is None:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class ThrottledRestAuthLoginView(LoginView):
    throttle_scope = 'dj_rest_auth'
    throttle_classes = [RestAuthLoginAccountThrottle, ScopedRateThrottle]


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

    The address is checked first, so a blocked address stops spending the
    account's budget. One address can therefore spend only the address limit,
    which is why the account limit in settings must stay well above it: that
    leaves the owner able to log in from elsewhere. Enough addresses together can
    still fill the account limit.
    """
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.method == 'POST':
            for throttle in (FormLoginAddressThrottle(), FormLoginAccountThrottle()):
                if not throttle.allow_request(request, None):
                    response = HttpResponse('Too many login attempts. Try again later.',
                                            status=429, content_type='text/plain')
                    # None when the rate was lowered while history existed.
                    wait = throttle.wait()
                    if wait is not None:
                        response['Retry-After'] = str(math.ceil(wait))
                    return response
        return view(request, *args, **kwargs)
    return wrapped
