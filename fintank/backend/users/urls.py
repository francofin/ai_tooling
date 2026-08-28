from django.urls import path, include
from .views import (
    register,
    get_current_user,
    get_current_user_profile,
    update_user,
    update_user_profile,
    update_my_avatar,
    change_password,
    list_avatar_presets,
)
from django.conf import settings
from django.conf.urls.static import static

app_name = "users"

urlpatterns = [
     # auth
    path("auth/register/", register, name="register"),

    # me
    path("users/me/", get_current_user, name="me"),
    path("users/me/update/", update_user, name="me-update"),
    path("users/me/change-password/", change_password, name="me-change-password"),

    # my profile
    path("users/me/profile/", get_current_user_profile, name="me-profile"),
    path("users/me/profile/update/", update_user_profile, name="me-profile-update"),
    path("users/me/profile/avatar/", update_my_avatar, name="me-profile-avatar"),
    path("avatar-presets/", list_avatar_presets, name="avatar-presets"),
]

# Serve media in DEBUG (avatars/resumes)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)