from django.urls import path
from .views import session_login, register_page, landing_page, logout_view, dashboard

app_name = "pages"
urlpatterns = [
    path("", landing_page, name="landing"),
    path("login/", session_login, name="login_uploader"),
    path("register/", register_page, name="register"),
    path("logout/", logout_view, name="logout_uploader"),
    path("dashboard/", dashboard, name="dashboard"),
]