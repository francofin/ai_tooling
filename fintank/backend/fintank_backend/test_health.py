from unittest import mock

from django.test import TestCase


class HealthzTests(TestCase):
    url = "/healthz/"

    def test_ok_when_db_and_cache_work(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "db": True, "redis": True})

    def test_503_when_db_fails(self):
        with mock.patch("fintank_backend.health.connection.cursor", side_effect=RuntimeError("boom")):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertIs(body["db"], False)
        self.assertIs(body["redis"], True)

    def test_503_when_cache_fails(self):
        with mock.patch("fintank_backend.health.cache.set", side_effect=RuntimeError("boom")):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertIs(body["redis"], False)
        self.assertIs(body["db"], True)

    def test_error_text_not_exposed(self):
        err = RuntimeError("could not connect to secret-host:5432")
        with mock.patch("fintank_backend.health.connection.cursor", side_effect=err), \
                mock.patch("fintank_backend.health.cache.set", side_effect=err):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret-host", response.content.decode())
