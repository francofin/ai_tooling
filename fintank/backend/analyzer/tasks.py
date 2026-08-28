from celery import shared_task
from .analyzer_utils.CorePerformanceTools import (get_biggest_gainers_and_losers, get_index_performance, get_index_charts, get_all_stock_names,
                                                  get_sector_performance_snapshot, get_company_profiles, get_universe_constituents_returns, get_etf_performance, get_crypto_performance,
                                                  get_all_universe_profiles, get_economic_data)
from .analyzer_utils.market_hours import is_market_open_now

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_index_performance(self):
    if not is_market_open_now():
        return "Market closed – skipping update"
    return get_index_performance()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_etf_performance(self):
    if not is_market_open_now():
        return "Market closed – skipping update"
    return get_etf_performance()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_crypto_performance(self):
    if not is_market_open_now():
        return "Market closed – skipping update"
    return get_crypto_performance()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def get_stock_names(self):
    return get_all_stock_names()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_market_datasets(self):
    if not is_market_open_now():
        return "Market closed – skipping update"
    return get_index_charts()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_gainers_losers(self):
    if not is_market_open_now():
        return "Market closed – skipping update"
    return get_biggest_gainers_and_losers()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def company_profiles(self):
    return get_company_profiles()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_sector_industry_snapshot(self):
    if not is_market_open_now():
        return "Market closed – skipping update"
    return get_sector_performance_snapshot()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_universe_profiles(self):
    return get_all_universe_profiles()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_economic_data(self):
    # No market-hours gate: FRED publishes on its own schedule and the spread
    # parquets are month-end, so nothing here changes intraday.
    return get_economic_data()

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=10)
def update_universe_constituent_performance(self):
    if not is_market_open_now():
        return "Market closed – skipping update"
    return get_universe_constituents_returns()

# web:    gunicorn project.wsgi
# worker: celery -A project worker -l info
# beat:   celery -A project beat -l info


# redis-server
# python manage.py runserver
# celery -A project worker -l info
# celery -A project beat -l info

#Can also run both worker and beat in one command for development
#celery -A fintank_backend worker -B -l info



# Pause tasks
# task = PeriodicTask.objects.get(name="Update Index Performance")
# task.enabled = False
# task.save()

# Resume tasks
# task = PeriodicTask.objects.get(name="Update Index Performance")
# task.enabled = True
# task.save()

#Redis check
# redis-cli ping should return PONG
# if not start with sudo service redis-server start
# use sudo systemctl status redis to check status
# use sudo systemctl stop redis to stop the server
# use sudo systemctl restart redis to restart the server# use sudo systemctl enable redis to enable redis to start on boot

