from django.core.cache import caches
from rozert_pay.limits import models as limit_models
from rozert_pay.payment.services import db_services

# Cache keys
ACTIVE_LIMITS_CACHE_KEY = "active_limits"
CACHE_INVALIDATION_KEY = "limits_cache_invalidation"
CACHE_TIMEOUT = 60  # 1 minute


def _get_cache_invalidation_version() -> int:
    """Get current cache invalidation version from Redis."""
    redis_cache = caches['default']
    version = redis_cache.get(CACHE_INVALIDATION_KEY)
    if version is None:
        version = 1
        redis_cache.set(CACHE_INVALIDATION_KEY, version, timeout=None)
    return version


def _get_cache_key() -> str:
    """Generate cache key with invalidation version."""
    version = _get_cache_invalidation_version()
    return f"{ACTIVE_LIMITS_CACHE_KEY}:v{version}"


def get_active_limits() -> (
    list[limit_models.CustomerLimit | limit_models.MerchantLimit]
):
    """Get active limits with 1-minute memory caching and Redis-based invalidation."""
    local_cache = caches['local_memory_cache']
    cache_key = _get_cache_key()
    
    # Try to get from local memory cache first
    cached_limits = local_cache.get(cache_key)
    if cached_limits is not None:
        return cached_limits
    
    # Cache miss - fetch from database
    active_limits = list(limit_models.CustomerLimit.objects.filter(status=True)) + list(
        limit_models.MerchantLimit.objects.filter(status=True)
    )
    
    # Cache in local memory for 1 minute
    local_cache.set(cache_key, active_limits, timeout=CACHE_TIMEOUT)
    
    return active_limits


def invalidate_limits_cache() -> None:
    """Globally invalidate limits cache across all processes using Redis."""
    redis_cache = caches['default']
    current_version = _get_cache_invalidation_version()
    redis_cache.set(CACHE_INVALIDATION_KEY, current_version + 1, timeout=None)


def on_transaction(
    trx: "db_services.LockedTransaction",
) -> tuple[bool, list[limit_models.LimitAlerts]]:
    """
    Returns: (is_transaction_declined, created_alerts)
    
    Проходим по всем активным лимитам, смотрим какие подходят
    Создаем LimitAlert
    Если нужно деклайним транзакцию
    id транзакции нужно привязать к LimitAlerts
    В limit alerts нужно сохранять все стат данные которые 
    использовались для триггеринга лимита
    Стат данные не кешируем
    """