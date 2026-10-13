import re
from datetime import datetime, timedelta, timezone

import requests
import json
from django.conf import settings
import boto3
import gzip
import s3fs
from django.core.cache import cache

CACHE_KEY = "home:news_articles:{item}:v2"

# The scraped topic feeds carry ages ("2h", "1d") relative to when the feed was
# written, not dates. Anchored to the file's S3 write time they become real
# timestamps; left alone they render as "Invalid Date" (or a stale "2h").
_RELATIVE_AGE = re.compile(r"^\s*(\d+)\s*(s|m|h|d|w|mo|y)\s*$", re.IGNORECASE)
_AGE_UNITS = {
    's': timedelta(seconds=1), 'm': timedelta(minutes=1), 'h': timedelta(hours=1),
    'd': timedelta(days=1), 'w': timedelta(weeks=1), 'mo': timedelta(days=30), 'y': timedelta(days=365),
}
_TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ",
                      "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d")


def published_at(article, scraped_at):
    """ISO 8601 publish time for an article, or None when it cannot be told.

    FMP feeds give `publishedDate`/`date` as "2026-09-18 21:00:16" with no zone;
    those stay zoneless (the page only shows the day). Relative ages resolve
    against `scraped_at` and come back in UTC.
    """
    raw = article.get('publishedDate') or article.get('datePublished') or article.get('date')
    if not raw or not isinstance(raw, str):
        return None

    age = _RELATIVE_AGE.match(raw)
    if age:
        if scraped_at is None:
            return None
        amount, unit = int(age.group(1)), age.group(2).lower()
        moment = scraped_at - amount * _AGE_UNITS[unit]
        return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for fmt in _TIMESTAMP_FORMATS:
        try:
            parsed = datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
        stamp = parsed.strftime("%Y-%m-%dT%H:%M:%S")
        return stamp + "Z" if raw.strip().endswith("Z") else stamp
    return None


def with_published_at(articles, scraped_at):
    if not isinstance(articles, list):
        return articles
    return [dict(a, published_at=published_at(a, scraped_at)) if isinstance(a, dict) else a
            for a in articles]


class GetNewsArticles:

    def __init__(self):
        self.file_names = {'fmp':'fmp_articles_articles.json', 'crypto':'crypto_articles_articles.json', 'stock':'stock_articles_articles.json', 'forex':'forex_articles_articles.json',
                           'econ':'econ_articles.json', 'global_news':'global_news_articles.json', 'tech':'tech_articles.json',
                            "macro":"macro_articles.json", 'politics':'politics_articles.json',
                            'energy':'energy_articles.json', 'oil':'oil_articles.json', 'mid_east':'mid_east_articles.json',
                            'south_america':'south_america_articles.json', 'us_stock':'us_stock_articles.json',
                            'japan_stock':'japan_stock_articles.json', 'china_stock':'china_stock_articles.json',
                            'canadian_stock':'canadian_stock_articles.json', 'eu_markets':'eu_markets_articles.json',
                            'africa_economy':'africa_economy_articles.json', 'basic_materials':'basic_materials_articles.json',
                            'industrials':'industrials_articles.json', 'utilities':'utilities_articles.json',
                            'pharmaceuticals':'pharmaceuticals_articles.json', 'consumer_trends':'consumer_trends_articles.json',
                            'financials':'financials_articles.json', 'real_estate':'real_estate_articles.json',
                            'communications':'communications_articles.json', 'digital_assets':'digital_assets_articles.json'}
        self.fmp_api = settings.FMP_API
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=str(settings.AWS_ACCESS_KEY_ID),
            aws_secret_access_key=str(settings.AWS_SECRET_ACCESS_KEY),
            region_name='us-east-1',
        )
        self.fs = s3fs.S3FileSystem(
            key=settings.AWS_ACCESS_KEY_ID,
            secret=settings.AWS_SECRET_ACCESS_KEY,
            client_kwargs={"region_name": "us-east-1"},
        )

    def file_decompressor(self, compressed_data):
        data = json.loads(gzip.decompress(compressed_data))
        return data
    
    def compress_series(self, context):
        return gzip.compress(json.dumps(context).encode("utf-8"))

    def get_news(self, search_term):
        result = self.s3_client.get_object(Bucket='thetradingfloor', Key=f"news_json_articles/{search_term}")
        text = result["Body"].read().decode()
        json_content = json.loads(text)
        return json_content
    
    def get_news_articles(self, source):
        bucket = 'thetradingfloor'
        key = f"news_json_articles/{source}"
        path = f"s3://{bucket}/{key}"
        raw_data = self.fs.open(path).read()
        articles = json.loads(raw_data)
        return with_published_at(articles, self._written_at(path))

    def _written_at(self, path):
        """When the feed file was last written -- the anchor for relative ages."""
        try:
            modified = self.fs.info(path).get('LastModified')
        except Exception:
            return None
        if isinstance(modified, datetime):
            return modified if modified.tzinfo else modified.replace(tzinfo=timezone.utc)
        return None
    
    def get_articles(self, item):
        search_term = self.file_names[item]
        articles = self.get_news(search_term)
        return articles

    def cache_single_article(self, item):
        data = self.get_news_articles(self.file_names[item])
        compressed = self.compress_series(data)
        cache.set(CACHE_KEY.format(item=item), compressed, timeout=86400)
        return compressed

    def cache_all_articles(self):
        for key in list(self.file_names.keys()):
            data = self.get_news_articles(self.file_names[key])
            compressed_news = self.compress_series(data)
            cache.set(
                CACHE_KEY.format(item=key),
                compressed_news,
                timeout=86400  # 24 hours
            )

        return "ok"