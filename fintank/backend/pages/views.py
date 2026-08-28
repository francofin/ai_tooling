# --- pages/views.py ---

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST

User = get_user_model()


def _staff_only(user):
    return user.is_active and (user.is_staff or user.is_superuser)

@require_POST
def session_login(request):
    username = (request.POST.get("username") or "").strip().lower()  # you store email in username
    password = request.POST.get("password") or ""
    next_url = request.POST.get("next")

    user = authenticate(request, username=username, password=password)
    if not user:
        messages.error(request, "Invalid email/username or password.")
        return redirect("pages:landing")
    
    # Admin-only portal
    if not (user.is_staff or user.is_superuser):
        messages.error(request, "You are not authorized to access this portal.")
        return redirect("pages:landing")

    login(request, user)
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        return redirect(next_url)
    return redirect("pages:landing")


@login_required(login_url="pages:landing")
@user_passes_test(_staff_only, login_url="pages:landing")
@require_http_methods(["GET", "POST"])
def register_page(request):
    """
    Admin-only registration:
      - Only staff/superusers may access.
      - Always creates staff users; superuser flag allowed only if current user is superuser.
    """
    if request.method == "GET":
        return render(request, "pages/register.html")

    first_name = (request.POST.get("first_name") or "").strip()
    last_name  = (request.POST.get("last_name") or "").strip()
    email      = (request.POST.get("email") or "").strip().lower()
    password   = request.POST.get("password") or ""
    password2  = request.POST.get("password2") or ""
    want_super = (request.POST.get("is_superuser") == "on")

    if not (first_name and last_name and email and password and password2):
        messages.error(request, _("All fields are required."))
        return redirect("pages:register")

    if password != password2:
        messages.error(request, _("Passwords do not match."))
        return redirect("pages:register")

    try:
        password_validation.validate_password(password)
    except Exception as exc:
        for e in getattr(exc, "error_list", []):
            messages.error(request, e)
        return redirect("pages:register")

    if User.objects.filter(email=email).exists() or User.objects.filter(username=email).exists():
        messages.error(request, _("A user with that email already exists."))
        return redirect("pages:register")

    # Create as staff by default (this portal is admin-only)
    is_staff = True
    is_superuser = want_super and request.user.is_superuser  # only superusers can create superusers

    user = User.objects.create_user(
        username=email,  # you login with username=email
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_staff=is_staff,
        is_superuser=is_superuser,
    )

    messages.success(
        request,
        _("User %(email)s created as %(role)s.") % {
            "email": email,
            "role": "superuser" if is_superuser else "staff"
        },
    )
    return redirect("pages:register")

def landing_page(request):
    return render(request, "pages/landing.html")

@require_POST
def logout_view(request):
    # why: POST-only to prevent CSRF-able GET logouts
    logout(request)
    return redirect("pages:landing")  # or "/"

# Example: protect a lightweight dashboard page
@login_required(login_url="pages:login")  # adjust if you have a login page
def dashboard(request):
    return render(request, "pages/services.html")
