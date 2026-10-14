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
from rest_framework_simplejwt.views import TokenObtainPairView, TokenVerifyView, TokenRefreshView


urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", include("users.urls", namespace="users")),
    path("api/", include("stockuploader.urls")),
    path("api/", include("analyzer.urls")),
    path("api/", include("backtester.urls")),
    path("api/", include("billing.urls")),
    path("api/", include("journal.urls")),
    path("api/", include("news.urls")),
    # Browsable API login
    path("api-auth/", include("rest_framework.urls")),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("api/auth/", include("dj_rest_auth.urls")),
    path("api/auth/registration/", include("dj_rest_auth.registration.urls")),
    path("accounts/", include("allauth.urls")),  # admin/social flows
      # pages (HTML)
    path("", include("pages.urls", namespace="pages")),
]


# Serve media in dev only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)