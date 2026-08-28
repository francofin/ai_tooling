"""Assign a random avatar to existing profiles that have none.

New users get one from the signup signal; this covers everyone who registered
before that existed. Idempotent -- profiles that already have an avatar are
skipped, so re-running never reshuffles anyone's choice.

Run `seed_avatar_presets` first, or there will be nothing to assign.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from users.avatars import assign_random_avatar
from users.models import AvatarPreset, UserProfile


class Command(BaseCommand):
    help = "Give a random avatar preset to profiles that do not have one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many profiles would be updated without writing.",
        )

    def handle(self, *args, **options):
        if not AvatarPreset.objects.filter(active=True).exists():
            self.stderr.write(
                self.style.ERROR("No active avatar presets. Run `seed_avatar_presets` first.")
            )
            return

        # No preset, and no uploaded image either -- an upload is a deliberate
        # choice and outranks a preset in avatar_url, so overwriting would be
        # both pointless and wrong.
        candidates = UserProfile.objects.filter(
            Q(preset_avatar__isnull=True) & (Q(avatar_upload="") | Q(avatar_upload__isnull=True))
        )

        if options["dry_run"]:
            self.stdout.write(f"{candidates.count()} profile(s) would be given an avatar.")
            return

        assigned = 0
        for profile in candidates.iterator():
            if assign_random_avatar(profile):
                assigned += 1

        self.stdout.write(self.style.SUCCESS(f"Assigned avatars to {assigned} profile(s)."))
