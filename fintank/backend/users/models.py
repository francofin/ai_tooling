from django.db import models
from django.core.validators import RegexValidator, EmailValidator
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
import uuid
from .managers import CustomUserManager
# Create your models here.

phone_validator = RegexValidator(
    regex=r"^[0-9+\-() .]{7,20}$",
    message = _("Enter a valid phone number."),
)

def avatar_upload_path(instance: "UserProfile", filename: str) -> str:
    # why: namespacing uploads per-user avoids collisions
    return f"avatars/uploads/user_{instance.user_id}/{filename}"


class UserRole(models.TextChoices):
    SUBSCRIBER = "subscriber", _("Subscriber")
    EMPLOYEE = "employee", _("Employee")
    ADMIN = "admin", _("Admin")
    INSTITUTIONAL_INVESTOR = "institutional_investor", _("Institutional Investor")

class AvatarPreset(models.Model):
    """Pre-generated avatars the product team can manage."""
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    image = models.ImageField(upload_to="avatars/presets/")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:100]
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name
    
class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='userprofile', on_delete=models.CASCADE)
    # store = models.OneToOneField(Store, on_delete=models.CASCADE, blank=True, null=True, default=None)
    company_number = models.CharField(max_length=300, blank=True, null=True, default=None)
    company_email = models.EmailField(max_length=300, blank=True, null=True, default=None, validators=[EmailValidator()])
    phone_number = models.CharField(max_length=20, blank=True, null=True, default=None, validators=[phone_validator])
    preset_avatar = models.ForeignKey(
        AvatarPreset, on_delete=models.SET_NULL, null=True, blank=True, related_name="profiles"
    )
    avatar_upload = models.ImageField(upload_to=avatar_upload_path, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True, default=None)
    stripe_account_id = models.CharField(max_length=500, null=True, blank=True)
    # Platform spec §3. Both default, so the migration needs no backfill.
    # REQUIRED: both are marked read_only in UserProfileSerializer -- that
    # serializer is fields="__all__" and is fed request.data directly, so
    # without the guard any authenticated user could PATCH themselves to 'pro'.
    subscription_tier = models.CharField(max_length=20, default='free', db_index=True)
    backtest_quota_override = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _("user profile")
        verbose_name_plural = _("user profiles")

    def __str__(self) -> str:
        # why: robust when names missing
        return f"Profile({getattr(self.user, 'username', None) or self.user.email})"

    @property
    def avatar_url(self) -> str | None:
        """Preferred avatar URL for display: uploaded > preset."""
        if self.avatar_upload:
            try:
                return self.avatar_upload.url
            except Exception:
                return None
        if self.preset_avatar and self.preset_avatar.image:
            try:
                return self.preset_avatar.image.url
            except Exception:
                return None
        return None
    

class CustomUser(AbstractUser):
    first_name = models.CharField(_("first name"), max_length=150, blank=False)
    last_name = models.CharField(_("last name"), max_length=150, blank=False)
    email = models.EmailField(_("email address"), unique=True)
    user_security_identifier = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    role = models.CharField(max_length=300, choices=UserRole.choices, default=UserRole.SUBSCRIBER, db_index=True,)
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional: plug in your custom manager to enforce names/emails on creation
    objects = CustomUserManager()

    REQUIRED_FIELDS = ["email", "first_name", "last_name"]  # USERNAME_FIELD remains "username"
    
    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        # Why: ensures readable display even if names are empty (shouldn't be).
        return self.get_full_name() or self.username or self.email or f"user:{self.pk}"
    
    @property
    def avatar_url(self) -> str | None:
        """Convenience: access avatar via user.profile."""
        prof = getattr(self, "userprofile", None)  # or 'userprofile' if that related_name is used
        return prof.avatar_url if prof else None