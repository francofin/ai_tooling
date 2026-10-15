from celery.schedules import crontab
from django.conf import settings
from django.test import SimpleTestCase


class BeatScheduleTests(SimpleTestCase):
    """Caches of pipeline outputs refresh at fixed UTC times just after the AWS
    jobs (news 09:30 daily; weekly data Saturdays from 10:00), not 24 h after
    whenever beat happened to start."""

    def test_news_cache_refreshes_after_the_news_job(self):
        entry = settings.CELERY_BEAT_SCHEDULE["update_news_articles_daily"]
        self.assertEqual(entry["schedule"], crontab(hour=10, minute=0))

    def test_market_data_caches_refresh_after_the_weekly_run(self):
        for name in ("update_universe_profiles_daily", "update_economic_data_daily"):
            entry = settings.CELERY_BEAT_SCHEDULE[name]
            self.assertEqual(entry["schedule"], crontab(hour=20, minute=0), name)
