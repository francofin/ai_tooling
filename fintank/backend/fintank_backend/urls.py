"""fintank_backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings

from .auth_views import (
    ThrottledRestAuthLoginView,
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
    ThrottledTokenVerifyView,
    limit_form_login,
)
from .health import healthz


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path('admin/login/', limit_form_login(admin.site.login)),
    path('admin/', admin.site.urls),
    path("api/", include("users.urls", namespace="users")),
    path("api/", include("stockuploader.urls")),
    path("api/", include("analyzer.urls")),
    path("api/", include("backtester.urls")),
    path("api/", include("billing.urls")),
    path("api/", include("journal.urls")),
    path("api/", include("news.urls")),
    path("api/auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/token/verify/", ThrottledTokenVerifyView.as_view(), name="token_verify"),
    path("api/auth/login/", ThrottledRestAuthLoginView.as_view(), name="rest_login"),
    path("api/auth/", include("dj_rest_auth.urls")),
    path("api/auth/registration/", include("dj_rest_auth.registration.urls")),
    path("accounts/", include("allauth.urls")),  # admin/social flows
      # pages (HTML)
    path("", include("pages.urls", namespace="pages")),
]


# Serve media and the browsable API's login in dev only
if settings.DEBUG:
    urlpatterns.append(path("api-auth/", include("rest_framework.urls")))
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)