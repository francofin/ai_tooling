# users/serializers.py
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import password_validation
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import CustomUser, UserProfile, AvatarPreset

class SignUpSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = CustomUser
        fields = ("first_name", "last_name", "email", "password", "password2", "user_security_identifier")
        read_only_fields = ("user_security_identifier",)
        extra_kwargs = {
            "first_name": {"required": True, "allow_blank": False},
            "last_name": {"required": True, "allow_blank": False},
            "email": {
                "required": True,
                "allow_blank": False,
                "validators": [UniqueValidator(queryset=CustomUser.objects.all())],
            },
            "password": {"required": True, "write_only": True, "min_length": 8, "style": {"input_type": "password"}},
        }

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        # Case-insensitive uniqueness guard (DB 'unique' may be case-sensitive on Postgres)
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(_("A user with that email already exists."))
        return value

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password2"):
            raise serializers.ValidationError({"password2": "Passwords do not match."})
        password_validation.validate_password(attrs["password"])
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("password2", None)
        email = validated_data.pop("email")
        # username=email for simplicity (your manager expects this)
        user = CustomUser.objects.create_user(username=email, email=email, password=password, **validated_data)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    avatar_url = serializers.CharField(read_only=True)

    class Meta:
        model = UserProfile
        fields = "__all__"
        extra_kwargs = {
            "stripe_account_id": {"write_only": True},  # avoid leaking sensitive IDs
            # Read-only, not excluded: the QuotaBanner displays tier and
            # remaining runs, it just must never set them. Tier changes come from
            # the admin or, later, a Stripe webhook -- never from request.data.
            "subscription_tier": {"read_only": True},
            "backtest_quota_override": {"read_only": True},
        }


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.CharField(read_only=True)

    class Meta:
        model = CustomUser
        fields = ("id", "first_name", "last_name", "email", "username", "role", "created_at", "user_security_identifier", "avatar_url")
        read_only_fields = ("id", "created_at", "user_security_identifier", "avatar_url")


class ProfileAvatarUpdateSerializer(serializers.ModelSerializer):
    """
    Update avatar via either a preset or a new upload, not both.
    """
    preset_avatar_id = serializers.IntegerField(required=False, allow_null=True)
    preset_avatar_slug = serializers.SlugField(required=False, allow_null=True)
    avatar_upload = serializers.ImageField(required=False, allow_null=True)
    clear_avatar = serializers.BooleanField(required=False, default=False)
    avatar_url = serializers.CharField(read_only=True)

    class Meta:
        model = UserProfile
        fields = (
            "preset_avatar_id",
            "preset_avatar_slug",
            "avatar_upload",
            "clear_avatar",
            "avatar_url",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Disallow passing both preset and upload together.
        has_preset = attrs.get("preset_avatar_id") is not None or attrs.get("preset_avatar_slug") is not None
        has_upload = attrs.get("avatar_upload") is not None
        if has_preset and has_upload:
            raise serializers.ValidationError(_("Choose either a preset avatar or upload a file, not both."))
        return attrs

    def _resolve_preset(self, attrs: dict[str, Any]) -> AvatarPreset | None:
        pid = attrs.pop("preset_avatar_id", None)
        pslug = attrs.pop("preset_avatar_slug", None)
        if pid is not None:
            return AvatarPreset.objects.filter(id=pid, active=True).first()
        if pslug is not None:
            return AvatarPreset.objects.filter(slug=pslug, active=True).first()
        return None

    @transaction.atomic
    def update(self, instance: UserProfile, validated_data: dict[str, Any]) -> UserProfile:
        # Clear explicitly
        if validated_data.pop("clear_avatar", False):
            if instance.avatar_upload:
                instance.avatar_upload.delete(save=False)  # cleanup file in storage
            instance.avatar_upload = None
            instance.preset_avatar = None

        # Handle upload
        new_upload = validated_data.pop("avatar_upload", None)
        if new_upload is not None:
            if instance.avatar_upload:
                instance.avatar_upload.delete(save=False)
            instance.avatar_upload = new_upload
            instance.preset_avatar = None

        # Handle preset
        preset = self._resolve_preset(validated_data)
        if preset is not None:
            if instance.avatar_upload:
                instance.avatar_upload.delete(save=False)
            instance.avatar_upload = None
            instance.preset_avatar = preset

        instance.save()
        return instance