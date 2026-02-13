from django.core.cache import caches
from rozert_pay.limits import models as limit_models
from rozert_pay.payment.services import db_services

# Cache configuration
ACTIVE_LIMITS_CACHE_KEY = "active_limits"
CACHE_TIMEOUT = 60  # 1 minute


def get_active_limits() -> (
    list[limit_models.CustomerLimit | limit_models.MerchantLimit]
):
    """Get active limits with 1-minute memory caching."""
    local_cache = caches["local_memory_cache"]

    # Try to get from local memory cache first
    cached_limits = local_cache.get(ACTIVE_LIMITS_CACHE_KEY)
    if cached_limits is not None:
        return cached_limits

    # Cache miss - fetch from database
    active_limits = list(limit_models.CustomerLimit.objects.filter(status=True)) + list(
        limit_models.MerchantLimit.objects.filter(status=True)
    )

    # Cache in local memory for 1 minute
    local_cache.set(ACTIVE_LIMITS_CACHE_KEY, active_limits, timeout=CACHE_TIMEOUT)

    return active_limits


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
