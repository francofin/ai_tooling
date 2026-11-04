import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

_CACHE_KEY = "healthz:probe"


def _check_db():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception as exc:
        # Class name only: exception text can contain hosts or credentials.
        logger.error("healthz db check failed: %s", type(exc).__name__)
        return False


def _check_cache():
    try:
        cache.set(_CACHE_KEY, "ok", 10)
        return cache.get(_CACHE_KEY) == "ok"
    except Exception as exc:
        logger.error("healthz cache check failed: %s", type(exc).__name__)
        return False


@require_GET
def healthz(request):
    """Liveness/readiness probe. Plain Django view: no DRF auth. Never returns error text."""
    db = _check_db()
    redis = _check_cache()
    healthy = db and redis
    return JsonResponse(
        {"status": "ok" if healthy else "unavailable", "db": db, "redis": redis},
        status=200 if healthy else 503,
    )
