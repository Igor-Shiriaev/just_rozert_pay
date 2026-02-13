import json
from typing import Union

from django.core.cache import caches
from django.core.cache.utils import make_template_fragment_key

from rozert_pay.limits import models as limit_models
from rozert_pay.payment.services import db_services

# Cache configuration
LIMITS_CACHE_KEY = "active_limits"
LIMITS_CACHE_TIMEOUT = 60  # 1 minute
LIMITS_INVALIDATION_CHANNEL = "limits_invalidation"

# Get cache instances
memory_cache = caches["local_memory_cache"]
redis_cache = caches["default"]


def get_active_limits() -> list[Union[limit_models.CustomerLimit, limit_models.MerchantLimit]]:
    """Get active limits with 1-minute memory caching and Redis-based global invalidation."""
    
    # Check if cache was invalidated via Redis
    invalidation_key = f"{LIMITS_CACHE_KEY}_invalidated"
    if redis_cache.get(invalidation_key):
        memory_cache.delete(LIMITS_CACHE_KEY)
        redis_cache.delete(invalidation_key)
    
    # Try to get from local memory cache first
    cached_limits = memory_cache.get(LIMITS_CACHE_KEY)
    if cached_limits is not None:
        return cached_limits
    
    # Fetch from database
    limits = list(limit_models.CustomerLimit.objects.filter(status=True)) + list(
        limit_models.MerchantLimit.objects.filter(status=True)
    )
    
    # Store in local memory cache for 1 minute
    memory_cache.set(LIMITS_CACHE_KEY, limits, LIMITS_CACHE_TIMEOUT)
    
    return limits


def invalidate_limits_cache() -> None:
    """Invalidate limits cache globally across all processes using Redis."""
    # Set invalidation flag in Redis - all processes will check this
    invalidation_key = f"{LIMITS_CACHE_KEY}_invalidated"
    redis_cache.set(invalidation_key, True, timeout=LIMITS_CACHE_TIMEOUT + 10)
    
    # Also clear local cache immediately
    memory_cache.delete(LIMITS_CACHE_KEY)


def on_transaction(
    trx: "db_services.LockedTransaction",
) -> tuple[bool, list[limit_models.LimitAlerts]]:
    """
    Returns: (is_transaction_declined, created_alerts)
    Проходим по всем активным лимитам, смотрим какие подходят
    Создаем LimitAlert
    Если нужно деклайним транзакцию
    id транзакции нужно привязать к LimitAlerts
    В limit alerts нужно сохранять все стат данные которые использовались для триггеринга лимита
    Стат данные не кешируем
    """