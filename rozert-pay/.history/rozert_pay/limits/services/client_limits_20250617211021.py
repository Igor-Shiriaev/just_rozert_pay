import time
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone
from rozert_pay.limits import models as limit_models
from rozert_pay.payment.services import db_services

# Cache configuration
_ACTIVE_LIMITS_CACHE_KEY = "active_limits"
_ACTIVE_LIMITS_CACHE_TTL = 60  # 1 minute
_REDIS_INVALIDATION_KEY = "limits_cache_invalidation"

# In-memory cache for active limits
_memory_cache: dict[str, Any] = {}


def get_active_limits() -> (
    list[limit_models.CustomerLimit | limit_models.MerchantLimit]
):
    # Check if we have a valid cached result
    cache_key = _ACTIVE_LIMITS_CACHE_KEY
    current_time = time.time()

    # Check Redis for cache invalidation signal
    if cache.get(_REDIS_INVALIDATION_KEY):
        _memory_cache.clear()
        cache.delete(_REDIS_INVALIDATION_KEY)

    # Check memory cache
    if cache_key in _memory_cache:
        cached_data, timestamp = _memory_cache[cache_key]
        if current_time - timestamp < _ACTIVE_LIMITS_CACHE_TTL:
            return cached_data

    # Cache miss - fetch from database
    active_limits = list(limit_models.CustomerLimit.objects.filter(active=True)) + list(
        limit_models.MerchantLimit.objects.filter(active=True)
    )

    # Cache the result
    _memory_cache[cache_key] = (active_limits, current_time)

    return active_limits


def invalidate_active_limits_cache() -> None:
    """Invalidate the active limits cache globally using Redis."""
    cache.set(_REDIS_INVALIDATION_KEY, True, timeout=120)  # Signal for 2 minutes
    _memory_cache.clear()


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
    active_limits = get_active_limits()
    created_alerts: list[limit_models.LimitAlerts] = []
    should_decline = False

    for limit in active_limits:
        if isinstance(limit, limit_models.CustomerLimit):
            alert = _check_customer_limit(trx, limit)
        elif isinstance(limit, limit_models.MerchantLimit):
            alert = _check_merchant_limit(trx, limit)
        else:
            continue

        if alert:
            created_alerts.append(alert)
            if limit.decline_on_exceed:
                should_decline = True

    return should_decline, created_alerts


def _check_customer_limit(
    trx: "db_services.LockedTransaction", limit: limit_models.CustomerLimit
) -> limit_models.LimitAlerts | None:
    """Check if customer limit is exceeded and create alert if needed."""
    if trx.customer_id != limit.customer_id:
        return None

    # Calculate period start time
    now = timezone.now()
    if limit.period == limit_models.ClientLimitPeriod.HOUR:
        period_start = now - timedelta(hours=1)
    elif limit.period == limit_models.ClientLimitPeriod.DAY:
        period_start = now - timedelta(days=1)
    else:
        return None

    # Get transactions in period for this customer
    customer_transactions = db_services.PaymentTransaction.objects.filter(
        customer_id=limit.customer_id, created_at__gte=period_start
    )

    # Check various limit types
    violation_data = {}
    is_violated = False

    # Check operation amount limits
    if limit.min_operation_amount and trx.amount < limit.min_operation_amount:
        violation_data["min_amount_violation"] = {
            "limit": str(limit.min_operation_amount),
            "transaction_amount": str(trx.amount),
        }
        is_violated = True

    if limit.max_operation_amount and trx.amount > limit.max_operation_amount:
        violation_data["max_amount_violation"] = {
            "limit": str(limit.max_operation_amount),
            "transaction_amount": str(trx.amount),
        }
        is_violated = True

    # Check successful operations count
    if limit.max_successful_operations:
        successful_count = customer_transactions.filter(status="SUCCESS").count()
        if successful_count >= limit.max_successful_operations:
            violation_data["successful_operations_violation"] = {
                "limit": limit.max_successful_operations,
                "current_count": successful_count,
                "period": limit.period,
            }
            is_violated = True

    # Check failed operations count
    if limit.max_failed_operations:
        failed_count = customer_transactions.filter(status="FAILED").count()
        if failed_count >= limit.max_failed_operations:
            violation_data["failed_operations_violation"] = {
                "limit": limit.max_failed_operations,
                "current_count": failed_count,
                "period": limit.period,
            }
            is_violated = True

    # Check total successful amount
    if limit.total_successful_amount:
        total_amount = (
            customer_transactions.filter(status="SUCCESS").aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        if total_amount >= limit.total_successful_amount:
            violation_data["total_amount_violation"] = {
                "limit": str(limit.total_successful_amount),
                "current_total": str(total_amount),
                "period": limit.period,
            }
            is_violated = True

    if is_violated:
        return limit_models.LimitAlerts.objects.create(
            customer_limit=limit,
            extra={
                "transaction_id": trx.id,
                "violation_data": violation_data,
                "transaction_amount": str(trx.amount),
                "customer_id": trx.customer_id,
                "period_start": period_start.isoformat(),
                "check_time": now.isoformat(),
            },
        )

    return None


def _check_merchant_limit(
    trx: "db_services.LockedTransaction", limit: limit_models.MerchantLimit
) -> limit_models.LimitAlerts | None:
    """Check if merchant limit is exceeded and create alert if needed."""
    # Check scope matching
    if limit.scope == limit_models.MerchantLimitScope.MERCHANT:
        if trx.wallet.wallet.merchant_id != limit.merchant_id:
            return None
    elif limit.scope == limit_models.MerchantLimitScope.WALLET:
        if trx.wallet_id != limit.wallet_id:
            return None
    else:
        return None

    # Calculate period start time
    now = timezone.now()
    if limit.validity_period == limit_models.LimitValidityPeriod.ONE_HOUR:
        period_start = now - timedelta(hours=1)
    elif limit.validity_period == limit_models.LimitValidityPeriod.TWENTY_FOUR_HOURS:
        period_start = now - timedelta(hours=24)
    else:
        return None

    # Get transactions in scope and period
    if limit.scope == limit_models.MerchantLimitScope.MERCHANT:
        transactions = db_services.PaymentTransaction.objects.filter(
            wallet__wallet__merchant_id=limit.merchant_id, created_at__gte=period_start
        )
    else:  # WALLET scope
        transactions = db_services.PaymentTransaction.objects.filter(
            wallet_id=limit.wallet_id, created_at__gte=period_start
        )

    violation_data = {}
    is_violated = False

    # Check different limit types based on limit_type
    if limit.limit_type == limit_models.LimitType.MAX_SUCCESSFUL_DEPOSITS:
        if limit.max_operations:
            successful_count = transactions.filter(
                status="SUCCESS", type="DEPOSIT"
            ).count()
            if successful_count >= limit.max_operations:
                violation_data["max_successful_deposits_violation"] = {
                    "limit": limit.max_operations,
                    "current_count": successful_count,
                }
                is_violated = True

    elif limit.limit_type == limit_models.LimitType.MAX_DECLINE_PERCENT:
        if limit.max_decline_percent:
            total_transactions = transactions.count()
            if total_transactions > 0:
                declined_count = transactions.filter(status="FAILED").count()
                decline_percent = (declined_count / total_transactions) * 100
                if decline_percent >= limit.max_decline_percent:
                    violation_data["decline_percent_violation"] = {
                        "limit": str(limit.max_decline_percent),
                        "current_percent": str(decline_percent),
                        "declined_count": declined_count,
                        "total_count": total_transactions,
                    }
                    is_violated = True

    elif limit.limit_type == limit_models.LimitType.MIN_SINGLE_OPERATION:
        if limit.min_amount and trx.amount < limit.min_amount:
            violation_data["min_single_operation_violation"] = {
                "limit": str(limit.min_amount),
                "transaction_amount": str(trx.amount),
            }
            is_violated = True

    elif limit.limit_type == limit_models.LimitType.MAX_SINGLE_OPERATION:
        if limit.max_amount and trx.amount > limit.max_amount:
            violation_data["max_single_operation_violation"] = {
                "limit": str(limit.max_amount),
                "transaction_amount": str(trx.amount),
            }
            is_violated = True

    elif limit.limit_type == limit_models.LimitType.TOTAL_DEPOSITS_PERIOD:
        if limit.total_amount:
            total_deposits = (
                transactions.filter(type="DEPOSIT", status="SUCCESS").aggregate(
                    total=Sum("amount")
                )["total"]
                or 0
            )
            if total_deposits >= limit.total_amount:
                violation_data["total_deposits_violation"] = {
                    "limit": str(limit.total_amount),
                    "current_total": str(total_deposits),
                }
                is_violated = True

    elif limit.limit_type == limit_models.LimitType.TOTAL_WITHDRAWALS_PERIOD:
        if limit.total_amount:
            total_withdrawals = (
                transactions.filter(type="WITHDRAWAL", status="SUCCESS").aggregate(
                    total=Sum("amount")
                )["total"]
                or 0
            )
            if total_withdrawals >= limit.total_amount:
                violation_data["total_withdrawals_violation"] = {
                    "limit": str(limit.total_amount),
                    "current_total": str(total_withdrawals),
                }
                is_violated = True

    if is_violated:
        return limit_models.LimitAlerts.objects.create(
            merchant_limit=limit,
            extra={
                "transaction_id": trx.id,
                "violation_data": violation_data,
                "transaction_amount": str(trx.amount),
                "merchant_id": trx.wallet.wallet.merchant_id,
                "wallet_id": trx.wallet_id,
                "period_start": period_start.isoformat(),
                "check_time": now.isoformat(),
                "limit_type": limit.limit_type,
                "scope": limit.scope,
            },
        )

    return None
