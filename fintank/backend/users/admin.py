from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import CustomUser, UserProfile, AvatarPreset


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    fk_name = "user"
    can_delete = False
    extra = 0
    fields = (
        ("preset_avatar", "avatar_upload"),
        "company_email",
        "company_number",
        "phone_number",
        "date_of_birth",
        "stripe_account_id",
        ("subscription_tier", "subscription_status", "subscription_interval"),
        ("current_period_end", "cancel_at_period_end"),
        ("stripe_customer_id", "stripe_subscription_id"),
        ("created_at", "updated_at"),
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "subscription_status",
        "subscription_interval",
        "current_period_end",
        "cancel_at_period_end",
        "stripe_customer_id",
        "stripe_subscription_id",
    )


@admin.register(CustomUser)
class UserAdmin(DjangoUserAdmin):
    inlines = [UserProfileInline]

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "role",
        "is_active",
        "is_staff",
        "date_joined",
        "created_at",
    )
    list_filter = ("role", "is_active", "is_staff", "is_superuser", "date_joined", "created_at")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (_("Roles"), {"fields": ("role",)}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined", "created_at")}),
        (_("Identifiers"), {"fields": ("user_security_identifier",)}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "email", "first_name", "last_name", "password1", "password2", "role")}),
    )
    readonly_fields = ("user_security_identifier", "created_at", "date_joined", "last_login")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "avatar_thumb", "company_email", "company_number", "updated_at")
    date_hierarchy = "updated_at"
    search_fields = ("user__username", "user__email", "company_email", "company_number")
    list_filter = ("updated_at",)

    readonly_fields = (
        "created_at",
        "updated_at",
        "avatar_preview",
        "subscription_status",
        "subscription_interval",
        "current_period_end",
        "cancel_at_period_end",
        "stripe_customer_id",
        "stripe_subscription_id",
    )
    fields = (
        "user",
        ("preset_avatar", "avatar_upload"),
        "avatar_preview",
        "company_email",
        "company_number",
        "phone_number",
        "date_of_birth",
        "stripe_account_id",
        ("subscription_tier", "subscription_status", "subscription_interval"),
        ("current_period_end", "cancel_at_period_end"),
        ("stripe_customer_id", "stripe_subscription_id"),
        ("created_at", "updated_at"),
    )

    def avatar_thumb(self, obj):
        url = obj.avatar_url
        return format_html('<img src="{}" style="height:32px;width:32px;border-radius:50%;" />', url) if url else "-"
    avatar_thumb.short_description = "Avatar"

    def avatar_preview(self, obj):
        url = obj.avatar_url
        return format_html('<img src="{}" style="max-height:120px;border-radius:12px;" />', url) if url else "—"
    avatar_preview.short_description = "Preview"


@admin.register(AvatarPreset)
class AvatarPresetAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "active", "preview", "updated_at")
    list_filter = ("active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    fields = ("name", "slug", "image", "active", ("created_at", "updated_at"))
    readonly_fields = ("created_at", "updated_at", "preview")

    def preview(self, obj):
        return format_html('<img src="{}" style="height:40px;width:40px;border-radius:50%;" />', obj.image.url) if obj.image else "—"
    preview.short_description = "Preview"