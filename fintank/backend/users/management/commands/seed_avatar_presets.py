"""Register the frontend's shipped avatar images as AvatarPreset rows.

The images themselves are Next static assets under
`public/images/split_avatars/`; this only records their paths so the picker can
list them and `UserProfile.preset_avatar` can point at one. Nothing is copied.

Idempotent: safe to re-run after adding images to the directory.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from users.models import AvatarPreset

# Relative to the repository root (the Next project), not to BASE_DIR, which is
# the Django project one level down.
AVATAR_DIR = Path("public/images/split_avatars")
URL_PREFIX = "/images/split_avatars"
SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class Command(BaseCommand):
    help = "Create or update AvatarPreset rows for the shipped avatar images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=None,
            help=f"Directory holding the avatar images (default: <repo>/{AVATAR_DIR}).",
        )
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Mark presets whose image is no longer on disk as inactive.",
        )

    def handle(self, *args, **options):
        if options["path"]:
            directory = Path(options["path"])
        else:
            # settings.BASE_DIR is backend/; the Next public/ dir is its sibling.
            directory = Path(settings.BASE_DIR).parent / AVATAR_DIR

        if not directory.is_dir():
            self.stderr.write(self.style.ERROR(f"No such directory: {directory}"))
            return

        files = sorted(p for p in directory.iterdir() if p.suffix.lower() in SUFFIXES)
        if not files:
            self.stderr.write(self.style.ERROR(f"No avatar images found in {directory}"))
            return

        created = updated = 0
        seen_slugs = set()

        for path in files:
            slug = path.stem.replace("_", "-").lower()
            seen_slugs.add(slug)
            # "avatar_017" -> "Avatar 017", which is what the admin list shows.
            name = path.stem.replace("_", " ").title()
            static_path = f"{URL_PREFIX}/{path.name}"

            preset, was_created = AvatarPreset.objects.update_or_create(
                slug=slug,
                defaults={"name": name, "static_path": static_path, "active": True},
            )
            created += was_created
            updated += not was_created

        message = f"Avatar presets: {created} created, {updated} updated ({len(files)} images)."
        self.stdout.write(self.style.SUCCESS(message))

        if options["deactivate_missing"]:
            stale = AvatarPreset.objects.filter(active=True).exclude(slug__in=seen_slugs)
            # Only presets backed by a static asset -- an admin-uploaded preset
            # has no file in this directory and must not be switched off by it.
            stale = stale.exclude(static_path__isnull=True).exclude(static_path="")
            count = stale.update(active=False)
            if count:
                self.stdout.write(self.style.WARNING(f"Deactivated {count} preset(s) with no image on disk."))
