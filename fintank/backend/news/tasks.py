from celery import shared_task
from .getNews import GetNewsArticles


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_news_articles(self):
    return GetNewsArticles().cache_all_articles()