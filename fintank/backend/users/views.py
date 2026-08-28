from __future__ import annotations
from django.contrib.auth import password_validation
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import CustomUser, UserProfile, AvatarPreset
from .serializers import (
    UserSerializer,
    UserProfileSerializer,
    SignUpSerializer,
    ProfileAvatarUpdateSerializer,
    AvatarPresetSerializer,
)

# ─────────────────────────────────────────────────────────────────────────────
# Auth / Registration
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    """
    Create a new user account.
    - Validates names, email uniqueness, password strength, password confirm.
    - Auto-creates UserProfile via signal.
    """
    serializer = SignUpSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        user = serializer.save()
    return Response(
        {"message": "Registered successfully.", "user": UserSerializer(user).data},
        status=status.HTTP_201_CREATED,
    )

# ─────────────────────────────────────────────────────────────────────────────
# Current user getters
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    """Return the authenticated user."""
    return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_current_user_profile(request):
    """Return the authenticated user's profile."""
    profile = getattr(request.user, "userprofile", None)
    if not profile:
        return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(UserProfileSerializer(profile).data, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Updates (account + profile)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def update_user(request):
    """
    Partially update current user's basic fields (first_name, last_name, email).
    If "password" provided, it is validated in the serializer at signup; here we just set it safely.
    """
    user: CustomUser = request.user
    data = dict(request.data)

    # Handle password separately (not part of UserSerializer fields)
    new_password = data.pop("password", None)
    serializer = UserSerializer(instance=user, data=data, partial=True)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        # Save non-password fields
        serializer.save()

        # Save password if present
        if new_password:
            # Minimal guard; for full validation reuse validators here if you want
            if len(new_password) < 8:
                return Response({"password": ["Ensure this field has at least 8 characters."]},
                                status=status.HTTP_400_BAD_REQUEST)
            user.set_password(new_password)
            user.save(update_fields=["password"])

    return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def change_password(request):
    """
    Securely change the current user's password.
    Requires old password and validates the new one using Django's validators.
    """
    user = request.user
    old_password = request.data.get("old_password") or ""
    new_password = request.data.get("new_password") or ""
    new_password2 = request.data.get("new_password2") or ""

    # Require correct old password
    if not user.check_password(old_password):
        return Response({"old_password": ["Incorrect password."]}, status=status.HTTP_400_BAD_REQUEST)

    # Confirm match
    if new_password != new_password2:
        return Response({"new_password2": ["Passwords do not match."]}, status=status.HTTP_400_BAD_REQUEST)

    # Prevent reuse of the same password
    if new_password == old_password:
        return Response({"new_password": ["New password must be different from the old password."]},
                        status=status.HTTP_400_BAD_REQUEST)

    # Strength validation
    try:
        password_validation.validate_password(new_password, user=user)
    except Exception as exc:
        # Return validator messages
        return Response({"new_password": [str(e) for e in exc.error_list]}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password"])

    # For JWT clients: refresh tokens after password change.
    return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def update_user_profile(request):
    """
    Partially update current user's profile fields.
    Accepts multipart/form-data for file fields (resume, avatar_upload via dedicated endpoint below).
    """
    profile: UserProfile | None = getattr(request.user, "userprofile", None)
    if not profile:
        return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = UserProfileSerializer(instance=profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        profile = serializer.save()
    return Response(UserProfileSerializer(profile).data, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Avatar: preset or upload (mutually exclusive)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def update_my_avatar(request):
    """
    Update avatar using either a preset OR an uploaded image.
    Body options:
      - preset_avatar_id=<int> OR preset_avatar_slug=<slug>
      - avatar_upload=<file>
      - clear_avatar=true
    """
    profile: UserProfile | None = getattr(request.user, "userprofile", None)
    if not profile:
        return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = ProfileAvatarUpdateSerializer(instance=profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        profile = serializer.save()
    return Response(UserProfileSerializer(profile).data, status=status.HTTP_200_OK)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_avatar_presets(request):
    """The avatar choices offered by the picker.

    Only active presets, and only ones that actually resolve to an image -- a
    row with neither an upload nor a static path would render as a broken tile.
    """
    presets = AvatarPreset.objects.filter(active=True)
    usable = [preset for preset in presets if preset.url]
    return Response(AvatarPresetSerializer(usable, many=True).data, status=status.HTTP_200_OK)
