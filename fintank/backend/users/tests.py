from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from .avatars import assign_random_avatar, pick_random_preset
from .models import AvatarPreset, UserProfile

User = get_user_model()


class UserFactoryMixin:
    """Creates users so their profile actually exists.

    `create_user_profile` runs on `transaction.on_commit`, and TestCase wraps
    each test in a transaction that is rolled back rather than committed, so
    without capturing the callbacks no profile is ever created and every lookup
    raises RelatedObjectDoesNotExist. Real signups commit normally.
    """

    def create_user(self, suffix):
        with self.captureOnCommitCallbacks(execute=True):
            return User.objects.create_user(
                username=f"u{suffix}", email=f"u{suffix}@example.com", password="pw",
                first_name="A", last_name="B",
            )


def make_avatar_dir(tmp, count=5):
    """A directory of fake avatar images for the seed command to scan."""
    for i in range(1, count + 1):
        (Path(tmp) / f"avatar_{i:03d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp


class AvatarPresetModelTests(TestCase):
    def test_url_prefers_static_path_when_no_upload(self):
        preset = AvatarPreset.objects.create(
            name="Avatar 001", static_path="/images/split_avatars/avatar_001.png"
        )
        self.assertEqual(preset.url, "/images/split_avatars/avatar_001.png")

    def test_url_is_none_when_nothing_is_set(self):
        preset = AvatarPreset.objects.create(name="Empty")
        self.assertIsNone(preset.url)

    def test_slug_is_derived_from_name(self):
        preset = AvatarPreset.objects.create(name="Avatar 007", static_path="/x.png")
        self.assertEqual(preset.slug, "avatar-007")


class AvatarUrlTests(UserFactoryMixin, TestCase):
    def setUp(self):
        self.user = self.create_user("1")
        self.profile = self.user.userprofile

    def test_profile_avatar_url_resolves_a_static_preset(self):
        """Regression: avatar_url used to read preset.image.url directly, which
        returns nothing for a preset backed by a static asset."""
        preset = AvatarPreset.objects.create(
            name="Static One", static_path="/images/split_avatars/avatar_002.png"
        )
        self.profile.preset_avatar = preset
        self.profile.save()
        self.assertEqual(self.profile.avatar_url, "/images/split_avatars/avatar_002.png")

    def test_avatar_url_is_none_without_any_avatar(self):
        self.profile.preset_avatar = None
        self.profile.save()
        self.assertIsNone(self.profile.avatar_url)


class RandomAssignmentTests(UserFactoryMixin, TestCase):
    def test_pick_returns_none_when_nothing_seeded(self):
        AvatarPreset.objects.all().delete()
        self.assertIsNone(pick_random_preset())

    def test_pick_ignores_inactive_presets(self):
        AvatarPreset.objects.create(name="Off", static_path="/a.png", active=False)
        self.assertIsNone(pick_random_preset())

    def test_signup_assigns_an_avatar_when_presets_exist(self):
        for i in range(5):
            AvatarPreset.objects.create(name=f"P{i}", static_path=f"/{i}.png")
        user = self.create_user("2")
        self.assertIsNotNone(user.userprofile.preset_avatar)

    def test_signup_succeeds_with_no_presets_seeded(self):
        """A missing avatar is cosmetic and must never fail a registration."""
        AvatarPreset.objects.all().delete()
        user = self.create_user("3")
        self.assertIsNone(user.userprofile.preset_avatar)
        self.assertIsNotNone(user.userprofile)

    def test_assignment_does_not_overwrite_an_existing_choice(self):
        chosen = AvatarPreset.objects.create(name="Chosen", static_path="/chosen.png")
        AvatarPreset.objects.create(name="Other", static_path="/other.png")
        user = self.create_user("4")
        profile = user.userprofile
        profile.preset_avatar = chosen
        profile.save()

        self.assertFalse(assign_random_avatar(profile))
        profile.refresh_from_db()
        self.assertEqual(profile.preset_avatar, chosen)

    def test_assignment_spreads_across_the_set(self):
        """Not a distribution test -- just that it is not pinned to one row."""
        for i in range(20):
            AvatarPreset.objects.create(name=f"S{i}", static_path=f"/{i}.png")
        picked = set()
        for _ in range(40):
            preset = pick_random_preset()
            picked.add(preset.id)
        self.assertGreater(len(picked), 1)


class SeedCommandTests(TestCase):
    def test_seeds_one_preset_per_image(self):
        with TemporaryDirectory() as tmp:
            make_avatar_dir(tmp, count=5)
            call_command("seed_avatar_presets", path=tmp, stdout=StringIO())
        self.assertEqual(AvatarPreset.objects.count(), 5)
        preset = AvatarPreset.objects.get(slug="avatar-001")
        self.assertEqual(preset.static_path, "/images/split_avatars/avatar_001.png")
        self.assertTrue(preset.active)

    def test_is_idempotent(self):
        with TemporaryDirectory() as tmp:
            make_avatar_dir(tmp, count=5)
            call_command("seed_avatar_presets", path=tmp, stdout=StringIO())
            call_command("seed_avatar_presets", path=tmp, stdout=StringIO())
        self.assertEqual(AvatarPreset.objects.count(), 5)

    def test_missing_directory_is_reported_not_raised(self):
        err = StringIO()
        call_command("seed_avatar_presets", path="/nonexistent/path", stdout=StringIO(), stderr=err)
        self.assertIn("No such directory", err.getvalue())


class BackfillCommandTests(UserFactoryMixin, TestCase):
    def _user(self, n):
        return self.create_user(f"b{n}")

    def test_backfills_only_profiles_without_an_avatar(self):
        # Created before any presets exist, so they get none at signup.
        users = [self._user(i) for i in range(3)]
        for u in users:
            self.assertIsNone(u.userprofile.preset_avatar)

        AvatarPreset.objects.create(name="P1", static_path="/1.png")
        call_command("backfill_avatars", stdout=StringIO())

        for u in users:
            u.userprofile.refresh_from_db()
            self.assertIsNotNone(u.userprofile.preset_avatar)

    def test_does_not_reshuffle_on_a_second_run(self):
        user = self._user(9)
        AvatarPreset.objects.create(name="P1", static_path="/1.png")
        AvatarPreset.objects.create(name="P2", static_path="/2.png")

        call_command("backfill_avatars", stdout=StringIO())
        user.userprofile.refresh_from_db()
        first = user.userprofile.preset_avatar_id

        call_command("backfill_avatars", stdout=StringIO())
        user.userprofile.refresh_from_db()
        self.assertEqual(user.userprofile.preset_avatar_id, first)

    def test_errors_clearly_when_no_presets_are_seeded(self):
        self._user(8)
        err = StringIO()
        call_command("backfill_avatars", stdout=StringIO(), stderr=err)
        self.assertIn("No active avatar presets", err.getvalue())

    def test_dry_run_writes_nothing(self):
        user = self._user(7)
        AvatarPreset.objects.create(name="P1", static_path="/1.png")
        call_command("backfill_avatars", "--dry-run", stdout=StringIO())
        user.userprofile.refresh_from_db()
        self.assertIsNone(user.userprofile.preset_avatar)
