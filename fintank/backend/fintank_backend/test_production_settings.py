import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = str(Path(__file__).resolve().parent.parent)

_PROBE = """
import json
from fintank_backend import settings as s
names = ["DEBUG", "ALLOWED_HOSTS", "CORS_ALLOWED_ORIGINS", "CSRF_TRUSTED_ORIGINS",
         "CACHES", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "DATABASES",
         "INSTALLED_APPS", "STORAGES", "MEDIA_URL", "SESSION_COOKIE_SECURE",
         "CSRF_COOKIE_SECURE", "SECURE_PROXY_SSL_HEADER", "SECURE_HSTS_SECONDS",
         "SECURE_SSL_REDIRECT", "REST_FRAMEWORK", "AUTH_THROTTLE_RATES"]
print(json.dumps({n: getattr(s, n, None) for n in names}, default=str))
"""


def load(extra_env):
    """Import settings in a clean subprocess and return selected values."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": BACKEND_DIR,
        "SECRET_KEY": "x",
        "DJANGO_SKIP_DOTENV": "1",
        **extra_env,
    }
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        env=env, cwd="/", capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


class ProductionSettingsTests(SimpleTestCase):
    def test_debug_defaults_to_false(self):
        self.assertIs(load({})["DEBUG"], False)

    def test_debug_true_only_when_set(self):
        self.assertIs(load({"DEBUG": "True"})["DEBUG"], True)

    def test_hosts_from_env(self):
        s = load({"ALLOWED_HOSTS": "api.thefintank.com,localhost"})
        self.assertEqual(s["ALLOWED_HOSTS"], ["api.thefintank.com", "localhost"])

    def test_cors_and_csrf_from_env(self):
        s = load({"CORS_ALLOWED_ORIGINS": "https://a.com,https://b.com",
                  "CSRF_TRUSTED_ORIGINS": "https://a.com"})
        self.assertEqual(s["CORS_ALLOWED_ORIGINS"], ["https://a.com", "https://b.com"])
        self.assertEqual(s["CSRF_TRUSTED_ORIGINS"], ["https://a.com"])

    def test_local_defaults_keep_localhost(self):
        s = load({})
        self.assertIn("localhost", s["ALLOWED_HOSTS"])
        self.assertIn("http://localhost:8020", s["CORS_ALLOWED_ORIGINS"])
        self.assertFalse(any("heroku" in h for h in s["ALLOWED_HOSTS"]))

    def test_redis_from_env_and_local_defaults(self):
        self.assertEqual(load({})["CACHES"]["default"]["LOCATION"], "redis://127.0.0.1:6379/15")
        self.assertEqual(load({})["CELERY_BROKER_URL"], "redis://localhost:6379/0")
        self.assertEqual(load({})["CELERY_RESULT_BACKEND"], "redis://localhost:6379/0")
        s = load({"CACHE_REDIS_URL": "redis://redis:6379/15",
                  "CELERY_BROKER_URL": "redis://redis:6379/0",
                  "CELERY_RESULT_BACKEND": "redis://redis:6379/1"})
        self.assertEqual(s["CACHES"]["default"]["LOCATION"], "redis://redis:6379/15")
        self.assertEqual(s["CELERY_BROKER_URL"], "redis://redis:6379/0")
        self.assertEqual(s["CELERY_RESULT_BACKEND"], "redis://redis:6379/1")

    def test_plain_postgres_engine_and_no_gis(self):
        s = load({})
        self.assertEqual(s["DATABASES"]["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertNotIn("django.contrib.gis", s["INSTALLED_APPS"])

    def test_sslmode_only_when_set(self):
        self.assertNotIn("OPTIONS", load({})["DATABASES"]["default"])
        s = load({"DATABASE_SSLMODE": "require"})
        self.assertEqual(s["DATABASES"]["default"]["OPTIONS"], {"sslmode": "require"})

    def test_media_goes_to_s3_when_not_debug(self):
        s = load({"AWS_BUCKET_NAME": "b"})
        self.assertEqual(s["STORAGES"]["default"]["BACKEND"], "storages.backends.s3.S3Storage")
        self.assertEqual(s["STORAGES"]["default"]["OPTIONS"]["location"], "media")
        self.assertEqual(s["MEDIA_URL"], "https://b.s3.amazonaws.com/media/")

    def test_media_location_from_env(self):
        s = load({"AWS_BUCKET_NAME": "b", "MEDIA_S3_LOCATION": "uploads"})
        self.assertEqual(s["STORAGES"]["default"]["OPTIONS"]["location"], "uploads")
        self.assertEqual(s["MEDIA_URL"], "https://b.s3.amazonaws.com/uploads/")

    def test_media_local_when_debug(self):
        s = load({"DEBUG": "True"})
        self.assertEqual(s["STORAGES"]["default"]["BACKEND"],
                         "django.core.files.storage.FileSystemStorage")

    def test_static_storage_preserved(self):
        self.assertIn("staticfiles", load({})["STORAGES"])
        self.assertEqual(load({})["STORAGES"]["staticfiles"]["BACKEND"],
                         "whitenoise.storage.CompressedStaticFilesStorage")

    def test_secure_flags_only_when_not_debug(self):
        s = load({})
        self.assertTrue(s["SESSION_COOKIE_SECURE"])
        self.assertTrue(s["CSRF_COOKIE_SECURE"])
        self.assertEqual(s["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])
        self.assertEqual(s["SECURE_HSTS_SECONDS"], 0)
        self.assertFalse(s["SECURE_SSL_REDIRECT"])
        self.assertEqual(load({"SECURE_HSTS_SECONDS": "60"})["SECURE_HSTS_SECONDS"], 60)
        self.assertIs(load({"DEBUG": "True"})["SESSION_COOKIE_SECURE"], False)


_LOGGING_PROBE = """
import logging
import django
django.setup()
logging.getLogger("django.request").error("request blew up")
logging.getLogger("analyzer.views").info("app info line")
try:
    raise RuntimeError("403 for url: https://fmp.example/x?a=1&apikey=SECRET1&b=2")
except RuntimeError:
    logging.getLogger("django.request").exception("with traceback")
"""


class ThrottleSettingsTests(SimpleTestCase):
    def test_outside_tests_the_real_limits_apply_behind_one_proxy(self):
        s = load({})
        self.assertEqual(s["REST_FRAMEWORK"]["DEFAULT_THROTTLE_RATES"], s["AUTH_THROTTLE_RATES"])
        self.assertEqual(s["REST_FRAMEWORK"]["NUM_PROXIES"], 1)


class LoggingSettingsTests(SimpleTestCase):
    def _stderr(self):
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": BACKEND_DIR,
            "SECRET_KEY": "x",
            "DJANGO_SKIP_DOTENV": "1",
            "DJANGO_SETTINGS_MODULE": "fintank_backend.settings",
        }
        out = subprocess.run(
            [sys.executable, "-c", _LOGGING_PROBE],
            env=env, cwd="/", capture_output=True, text=True, check=True,
        )
        return out.stderr

    def test_with_debug_false_request_errors_and_app_logs_reach_the_console(self):
        stderr = self._stderr()
        self.assertIn("request blew up", stderr)
        self.assertIn("app info line", stderr)

    def test_console_output_redacts_keys_even_in_tracebacks(self):
        stderr = self._stderr()
        self.assertIn("with traceback", stderr)
        self.assertIn("RuntimeError", stderr)
        self.assertNotIn("SECRET1", stderr)
        self.assertIn("apikey=[REDACTED]&b=2", stderr)

    def test_root_and_django_log_to_console_at_info(self):
        from django.conf import settings
        self.assertEqual(settings.LOGGING["root"]["handlers"], ["console"])
        self.assertEqual(settings.LOGGING["root"]["level"], "INFO")
        self.assertEqual(settings.LOGGING["loggers"]["django"]["level"], "INFO")
        self.assertEqual(settings.LOGGING["loggers"]["django"]["handlers"], ["console"])

    def test_the_test_run_itself_stays_quiet(self):
        from django.conf import settings
        self.assertEqual(settings.LOGGING["handlers"]["console"]["level"], "CRITICAL")

    def test_celery_handlers_get_redaction_and_keep_their_format(self):
        import io
        import logging
        from fintank_backend.celery import redact_worker_logs
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("WORKER %(message)s"))
        logger = logging.Logger("celery-format-test")
        logger.addHandler(handler)

        redact_worker_logs(logger=logger)
        logger.error("failed url?apikey=SECRET2")

        self.assertEqual(stream.getvalue().strip(), "WORKER failed url?apikey=[REDACTED]")


class GunicornLoggingTests(SimpleTestCase):
    def test_access_log_goes_to_stdout(self):
        dockerfile = (Path(BACKEND_DIR) / "Dockerfile").read_text()
        self.assertIn('"--access-logfile", "-"', dockerfile)
