from datetime import datetime, timezone

from django.test import SimpleTestCase

from news.getNews import published_at, with_published_at

SCRAPED = datetime(2026, 9, 21, 1, 10, 42, tzinfo=timezone.utc)


class PublishedAtTests(SimpleTestCase):
    """Every feed's date shape becomes an ISO timestamp the browser can parse."""

    def test_relative_ages_resolve_against_the_scrape_time(self):
        cases = {
            '22s': '2026-09-21T01:10:20Z',
            '55m': '2026-09-21T00:15:42Z',
            '7h': '2026-09-20T18:10:42Z',
            '1d': '2026-09-20T01:10:42Z',
            '2w': '2026-09-07T01:10:42Z',
        }
        for raw, expected in cases.items():
            self.assertEqual(published_at({'date': raw}, SCRAPED), expected, raw)

    def test_fmp_timestamps_become_iso_without_inventing_a_zone(self):
        self.assertEqual(published_at({'date': '2026-09-18 21:00:16'}, SCRAPED), '2026-09-18T21:00:16')
        self.assertEqual(published_at({'publishedDate': '2026-09-20 20:46:49'}, SCRAPED),
                         '2026-09-20T20:46:49')

    def test_explicit_utc_is_kept(self):
        self.assertEqual(published_at({'date': '2026-09-18T21:00:16Z'}, SCRAPED), '2026-09-18T21:00:16Z')

    def test_unknown_shapes_and_missing_anchor_give_none(self):
        self.assertIsNone(published_at({'date': 'yesterday'}, SCRAPED))
        self.assertIsNone(published_at({}, SCRAPED))
        self.assertIsNone(published_at({'date': None}, SCRAPED))
        self.assertIsNone(published_at({'date': '3h'}, None))

    def test_articles_keep_their_fields(self):
        articles = with_published_at([{'title': 'A', 'date': '1h'}], SCRAPED)
        self.assertEqual(articles, [{'title': 'A', 'date': '1h', 'published_at': '2026-09-21T00:10:42Z'}])
        self.assertEqual(with_published_at({'not': 'a list'}, SCRAPED), {'not': 'a list'})
