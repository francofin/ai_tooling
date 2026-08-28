# users/signals.py
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .avatars import assign_random_avatar
from .models import CustomUser, UserProfile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance: CustomUser, created: bool, **kwargs) -> None:
    """
    Create a blank profile exactly once when the user is created.
    Using on_commit avoids creating a profile for rolled-back users.
    """
    if not created:
        return

    def _create():
        profile, was_created = UserProfile.objects.get_or_create(user=instance)
        if was_created:
            # Cosmetic, and deliberately non-fatal: a registration must not fail
            # because the avatar table is empty or unreachable.
            try:
                assign_random_avatar(profile)
            except Exception:
                logger.exception("Could not assign a random avatar to %s", instance.pk)

    transaction.on_commit(_create)