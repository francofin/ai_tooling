from __future__ import annotations
from typing import Any
from django.contrib.auth.models import UserManager
from django.core.exceptions import ValidationError

class CustomUserManager(UserManager):
    """Require first_name/last_name and normalize email; default username=email (simplest)."""

    def get_by_natural_key(self, username):
        """
        Case-insensitive lookup on the login field.
        Works whether you keep USERNAME_FIELD='username' (where you store the email)
        or switch to USERNAME_FIELD='email'.
        """
        field = self.model.USERNAME_FIELD  # 'username' by default
        return self.get(**{f"{field}__iexact": username})

    def _require_names(self, first_name: str | None, last_name: str | None) -> None:
        if not first_name or not first_name.strip():
            raise ValidationError("first_name is required.")
        if not last_name or not last_name.strip():
            raise ValidationError("last_name is required.")

    def _normalize_email(self, email: str | None) -> str:
        if not email:
            raise ValidationError("email is required.")
        return self.normalize_email(email).lower()

    def create_user(self, username: str | None = None, email: str | None = None,
                    password: str | None = None, **extra_fields: Any):
        if not password:
            raise ValidationError("password is required.")
        email = self._normalize_email(email)
        first_name = extra_fields.get("first_name")
        last_name = extra_fields.get("last_name")
        self._require_names(first_name, last_name)
        username = username or email  # keep username login path simple
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        username: str | None = None,
        email: str | None = None,
        password: str | None = None,
        **extra_fields: Any,
    ):
        if not password:
            raise ValidationError("password is required for superuser.")
        # Ensure flags first, then delegate to create_user to keep logic DRY.
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValidationError("Superuser must have is_staff=True and is_superuser=True.")

        email = self._normalize_email(email)

        # username defaults to email for consistency
        return self.create_user(username=username or email, email=email, password=password, **extra_fields)
