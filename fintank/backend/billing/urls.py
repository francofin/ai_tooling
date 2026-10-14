"""Every app mounts at path("api/", include(...)), so routes carry billing/."""
from django.urls import path

from . import views

urlpatterns = [
    path('billing/subscription/', views.subscription_view, name='billing_subscription'),
    path('billing/checkout/', views.checkout_view, name='billing_checkout'),
    path('billing/portal/', views.portal_view, name='billing_portal'),
    path('billing/webhook/', views.stripe_webhook, name='billing_webhook'),
]
