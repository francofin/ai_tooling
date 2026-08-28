"""Random avatar assignment.

Shared by the signup signal and the backfill command so a new user and a
backfilled one are given avatars the same way.
"""

from __future__ import annotations

import random

from .models import AvatarPreset, UserProfile


def pick_random_preset() -> AvatarPreset | None:
    """An active preset chosen at random, or None if none are seeded.

    Reads the ids and chooses in Python rather than using `order_by('?')`: on
    PostgreSQL that sorts the whole table by a random value, and this is called
    on every signup. The preset set is small and changes rarely, so pulling the
    id list is far cheaper.

    Returns None rather than raising when nothing is seeded -- a missing avatar
    is cosmetic and must never be able to fail a registration.
    """
    ids = list(AvatarPreset.objects.filter(active=True).values_list("id", flat=True))
    if not ids:
        return None
    return AvatarPreset.objects.filter(id=random.choice(ids)).first()


def assign_random_avatar(profile: UserProfile) -> bool:
    """Give `profile` a random preset if it has no avatar yet.

    Leaves a profile that already has an uploaded image or a chosen preset
    untouched, so this is safe to run over existing users.

    Returns True if an avatar was assigned.
    """
    if profile.avatar_upload or profile.preset_avatar_id:
        return False

    preset = pick_random_preset()
    if preset is None:
        return False

    profile.preset_avatar = preset
    profile.save(update_fields=["preset_avatar", "updated_at"])
    return True
