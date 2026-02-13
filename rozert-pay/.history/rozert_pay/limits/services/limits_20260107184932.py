import datetime
import logging
import typing as ty
from collections import defaultdict
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, TypedDict, cast

from django.db import transaction
from rozert_pay.common import const
from rozert_pay.common.helpers.cache import (
    CacheKey,
    memory_cache_get_set,
    memory_cache_invalidate,
)
from rozert_pay.limits import const as limit_const
from rozert_pay.limits import models as limit_models
from rozert_pay.limits.const import (
    SLACK_CHANNEL_NAME_CRITICAL_LIMITS,
    SLACK_CHANNEL_NAME_REGULAR_LIMITS,
    LimitPeriod,
)
from rozert_pay.limits.models.common import LimitCategory
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit
from rozert_pay.limits.services.utils import (
    FilteredOutLimit,
    construct_notification_message,
)
from rozert_pay.limits.tasks import notify_in_slack
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services import db_services, event_logs
from rozert_pay.risk_lists.const import ListType
from rozert_pay.risk_lists.services.checker import is_customer_in_list

if TYPE_CHECKING:
    from rozert_pay.payment.systems import base_controller


logger = logging.getLogger(__name__)


class CustomerLimitTransactionData(TypedDict):
    status: str
    amount: Decimal


class MerchantLimitTransactionData(TypedDict):
    status: str
    amount: Decimal
    type: str
    created_at: datetime.datetime


ACTIVE_LIMITS_CACHE_KEY: CacheKey = CacheKey("active_limits")
CACHE_TIMEOUT = timedelta(minutes=1)  # 1 minute


def invalidate_limits_cache() -> None:
    """Both in memory and redis cache."""
    memory_cache_invalidate(ACTIVE_LIMITS_CACHE_KEY)


def get_active_limits() -> (
    list[limit_models.CustomerLimit | limit_models.MerchantLimit]
):
    def _fetch_active_limits() -> (
        list[limit_models.CustomerLimit | limit_models.MerchantLimit]
    ):
        return list(limit_models.CustomerLimit.objects.filter(active=True)) + list(
            limit_models.MerchantLimit.objects.filter(active=True)
        )

    return memory_cache_get_set(
        key=ACTIVE_LIMITS_CACHE_KEY,
        tp=list[limit_models.CustomerLimit | limit_models.MerchantLimit],
        on_miss=_fetch_active_limits,
        ttl=CACHE_TIMEOUT,
    )


def _should_check_customer_limit(
    limit: limit_models.CustomerLimit,
    trx: PaymentTransaction,
    is_customer_in_gray_list: bool,
) -> tuple[bool, str | None]:
    if not trx.customer:
        return False, "transaction has no customer"

    if trx.customer != limit.customer:
        return False, "transaction customer does not match limit customer"

    if limit.category == LimitCategory.BUSINESS:
        if not (trx.customer.risk_control and is_customer_in_gray_list):
            return True, None
        return (
            False,
            "business limit but customer has risk_control and the customer is in gray_list",
        )

    if limit.category == LimitCategory.RISK:
        if trx.customer.risk_control and is_customer_in_gray_list:
            return True, None
        return (
            False,
            "risk limit but customer lacks risk_control or the customer is not in gray_list",
        )

    return False, f"unknown category: {limit.category}"


def _should_check_merchant_limit(
    limit: limit_models.MerchantLimit,
    trx: PaymentTransaction,
) -> tuple[bool, str | None]:
    does_limit_belong_to_merchant = bool(
        limit.scope == limit_models.MerchantLimitScope.MERCHANT
        and trx.wallet.wallet.merchant_id == limit.merchant_id
    )
    does_limit_belong_to_wallet = bool(
        limit.scope == limit_models.MerchantLimitScope.WALLET
        and trx.wallet.wallet_id == limit.wallet_id
    )
    if not (does_limit_belong_to_merchant or does_limit_belong_to_wallet):
        if not does_limit_belong_to_merchant:
            return False, "limit does not belong to merchant"
        if not does_limit_belong_to_wallet:
            return False, "limit does not belong to wallet"

    if limit.category == LimitCategory.BUSINESS:
        return True, None

    has_risk_control = bool(
        (does_limit_belong_to_wallet and trx.wallet.wallet.risk_control)
        or (does_limit_belong_to_merchant and trx.wallet.wallet.merchant.risk_control)
    )

    if has_risk_control:
        return True, None

    if limit.category == LimitCategory.GLOBAL_RISK:
        return False, "global_risk limit but risk_control not enabled"
    return False, "risk limit but risk_control not enabled"


def _process_transaction_limits(
    trx: PaymentTransaction,
) -> tuple[bool, list[limit_models.LimitAlert]]:
    active_limits: Sequence[
        limit_models.CustomerLimit | limit_models.MerchantLimit
    ] = get_active_limits()

    logger.info(
        "Processing transaction: Found active limits",
        extra={
            "transaction_id": trx.id,
            "active_limits_count": len(active_limits),
            "customer_id": trx.customer_id,
            "merchant_id": trx.wallet.wallet.merchant_id,
            "wallet_id": trx.wallet_id,
        },
    )

    is_customer_in_gray_list: bool | None = (
        (is_customer_in_list(trx.customer, ListType.GRAY) if trx.customer else False)
        if active_limits
        else None
    )

    limits_to_check: list[limit_models.CustomerLimit | limit_models.MerchantLimit] = []
    filtered_out_customer_limits: list[FilteredOutLimit] = []
    filtered_out_merchant_limits: list[FilteredOutLimit] = []

    for limit in active_limits:
        is_customer_in_gray_list = cast(bool, is_customer_in_gray_list)
        if isinstance(limit, limit_models.CustomerLimit):
            if not trx.customer:  # pragma: no cover
                filtered_out_customer_limits.append(
                    FilteredOutLimit(limit=limit, reason="transaction has no customer")
                )
            else:
                should_check, reason = _should_check_customer_limit(
                    limit,
                    trx,
                    is_customer_in_gray_list,
                )
                if should_check:
                    limits_to_check.append(limit)
                else:  # pragma: no cover
                    filtered_out_customer_limits.append(
                        FilteredOutLimit(limit=limit, reason=reason)
                    )
        elif isinstance(limit, limit_models.MerchantLimit):
            should_check, reason = _should_check_merchant_limit(limit, trx)
            if should_check:
                limits_to_check.append(limit)
            else:  # pragma: no cover
                filtered_out_merchant_limits.append(
                    FilteredOutLimit(limit=limit, reason=reason)
                )

    if filtered_out_customer_limits:  # pragma: no cover
        logger.info(
            "Filtered out customer limits",
            extra={
                "transaction_id": trx.id,
                "filtered_count": len(filtered_out_customer_limits),
                "filtered_customer_limits": [
                    {
                        "limit_id": filtered_out_limit.limit.id,
                        "category": filtered_out_limit.limit.category,
                        "reason": filtered_out_limit.reason,
                    }
                    for filtered_out_limit in filtered_out_customer_limits
                    if isinstance(filtered_out_limit.limit, limit_models.CustomerLimit)
                ],
                "filtered_merchant_limits": [
                    {
                        "limit_id": filtered_out_limit.limit.id,
                        "limit_type": filtered_out_limit.limit.limit_type,
                        "category": filtered_out_limit.limit.category,
                        "reason": filtered_out_limit.reason,
                    }
                    for filtered_out_limit in filtered_out_merchant_limits
                    if isinstance(filtered_out_limit.limit, limit_models.MerchantLimit)
                ],
            },
        )

    if filtered_out_merchant_limits:  # pragma: no cover
        assert all(
            isinstance(filtered_out_limit.limit, limit_models.MerchantLimit)
            for filtered_out_limit in filtered_out_merchant_limits
        )
        logger.info(
            "Filtered out merchant limits",
            extra={
                "transaction_id": trx.id,
                "filtered_count": len(filtered_out_merchant_limits),
                "filtered_limits": [
                    {
                        "limit_id": filtered_out_limit.limit.id,
                        "limit_type": (
                            filtered_out_limit.limit.limit_type
                            if isinstance(
                                filtered_out_limit.limit, limit_models.MerchantLimit
                            )
                            else None
                        ),
                        "category": filtered_out_limit.limit.category,
                        "reason": filtered_out_limit.reason,
                    }
                    for filtered_out_limit in filtered_out_merchant_limits
                ],
            },
        )

    logger.info(
        "After initial filtering: limits to check",
        extra={
            "transaction_id": trx.id,
            "limits_to_check_count": len(limits_to_check),
            "customer_limits_count": sum(
                1
                for lim in limits_to_check
                if isinstance(lim, limit_models.CustomerLimit)
            ),
            "merchant_limits_count": sum(
                1
                for lim in limits_to_check
                if isinstance(lim, limit_models.MerchantLimit)
            ),
        },
    )

    (
        limits_with_resolved_customer_and_merchant_conflicts,
        risk_global_filtered,
    ) = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(limits_to_check)

    if risk_global_filtered:  # pragma: no cover
        logger.info(
            "Risk/GlobalRisk conflict resolution filtered out limits",
            extra={
                "transaction_id": trx.id,
                "filtered_count": len(risk_global_filtered),
                "filtered_limits": [
                    {
                        "limit_id": limit.id,
                        "limit_type": limit.limit_type,
                        "category": limit.category,
                        "reason": reason,
                    }
                    for limit, reason in risk_global_filtered
                ],
            },
        )

    (
        limits_with_resolved_all_type_of_conflicts,
        customer_merchant_filtered,
    ) = _resolve_customer_and_merchant_limit_conflicts(
        limits_with_resolved_customer_and_merchant_conflicts
    )

    if customer_merchant_filtered:  # pragma: no cover
        logger.info(
            "Customer/Merchant conflict resolution filtered out limits",
            extra={
                "transaction_id": trx.id,
                "filtered_count": len(customer_merchant_filtered),
                "filtered_limits": [
                    {
                        "limit_id": lim.id,
                        "limit_type": lim.limit_type,
                        "category": lim.category,
                        "reason": reason,
                    }
                    for lim, reason in customer_merchant_filtered
                ],
            },
        )

    logger.info(
        "Final limits to check after all filtering",
        extra={
            "transaction_id": trx.id,
            "limit_ids": [
                limit.id for limit in limits_with_resolved_all_type_of_conflicts
            ],
        },
    )

    all_triggered_alerts: list[limit_models.LimitAlert] = []
    for limit in limits_with_resolved_all_type_of_conflicts:
        is_limit_triggered: bool
        triggers_data: dict[str, str]

        if isinstance(limit, limit_models.CustomerLimit):
            is_limit_triggered, triggers_data = _check_customer_limit(limit, trx)
        elif isinstance(limit, limit_models.MerchantLimit):
            is_limit_triggered, triggers_data = _check_merchant_limit(limit, trx)
        else:
            raise ValueError(f"Invalid limit type: {type(limit)}")

        if is_limit_triggered:
            alert = limit_models.LimitAlert(
                customer_limit=(
                    limit if isinstance(limit, limit_models.CustomerLimit) else None
                ),
                merchant_limit=(
                    limit if isinstance(limit, limit_models.MerchantLimit) else None
                ),
                transaction=trx,
                is_active=True,
                extra=triggers_data,
            )
            all_triggered_alerts.append(alert)

    if all_triggered_alerts:
        with transaction.atomic():
            for alert in all_triggered_alerts:
                alert.save()
                limit = cast(
                    CustomerLimit | MerchantLimit,
                    alert.customer_limit or alert.merchant_limit,
                )
                if limit and limit.notification_groups.exists():
                    alert.notification_groups.set(limit.notification_groups.all())

        _notify_about_alerts(all_triggered_alerts)

    is_declined: bool = any(
        (alert.customer_limit and alert.customer_limit.decline_on_exceed)
        or (alert.merchant_limit and alert.merchant_limit.decline_on_exceed)
        for alert in all_triggered_alerts
    )

    logger.info(
        "Limit processing complete",
        extra={
            "transaction_id": trx.id,
            "alerts_triggered_count": len(all_triggered_alerts),
            "transaction_declined": is_declined,
        },
    )

    return is_declined, all_triggered_alerts


def check_limits_and_maybe_decline_transaction(
    trx: PaymentTransaction,
    controller: "base_controller.PaymentSystemController[ty.Any, ty.Any]",
) -> bool:
    # NOTE: Returns is_declined
    is_declined, all_triggered_limit_alerts = _process_transaction_limits(trx)

    if is_declined:
        decline_on_exceed_limit_ids = [
            str(alert.customer_limit.id)
            for alert in all_triggered_limit_alerts
            if alert.customer_limit and alert.customer_limit.decline_on_exceed
        ]
        decline_on_exceed_limit_ids.extend(
            [
                str(alert.merchant_limit.id)
                for alert in all_triggered_limit_alerts
                if alert.merchant_limit and alert.merchant_limit.decline_on_exceed
            ]
        )
        decline_reason = f"Declined by limits: {', '.join(decline_on_exceed_limit_ids)}"
        with transaction.atomic():
            # TODO: lock transactions in-place to prevent additional refresh
            locked_trx = db_services.get_transaction(for_update=True, trx_id=trx.id)
            controller.fail_transaction(
                trx=locked_trx,
                decline_code=const.TransactionDeclineCodes.LIMITS_DECLINE,
                decline_reason=decline_reason,
            )
        # refresh original transaction
        trx.refresh_from_db()

        alerts_with_decline_on_exceed = [
            alert
            for alert in all_triggered_limit_alerts
            if (alert.customer_limit and alert.customer_limit.decline_on_exceed)
            or (alert.merchant_limit and alert.merchant_limit.decline_on_exceed)
        ]

        event_logs.create_transaction_log(
            trx_id=trx.id,
            event_type=const.EventType.DECLINED_BY_LIMIT,
            description=f"Transaction {trx.id} declined by limits",
            extra={
                str(index): alert.extra
                for index, alert in enumerate(alerts_with_decline_on_exceed)
            },
        )
        return True
    return False


def _check_customer_limit(
    limit: limit_models.CustomerLimit,
    trx: PaymentTransaction,
) -> tuple[bool, dict[str, str]]:
    logger.info(
        "Checking customer limit",
        extra={
            "customer": limit.customer,
            "trx_id": trx.id,
            "limit_id": limit.id,
        },
    )
    is_limit_triggered = False
    triggers_data: dict[str, str] = {}

    if limit.min_operation_amount and trx.amount < limit.min_operation_amount:
        is_limit_triggered = True
        triggers_data[
            limit_const.VERBOSE_NAME_MIN_AMOUNT_SINGLE_OPERATION
        ] = f"Transaction amount {trx.amount} is less than limit {limit.min_operation_amount}"

    if limit.max_operation_amount and trx.amount > limit.max_operation_amount:
        is_limit_triggered = True
        triggers_data[
            limit_const.VERBOSE_NAME_MAX_AMOUNT_SINGLE_OPERATION
        ] = f"Transaction amount {trx.amount} is greater than limit {limit.max_operation_amount}"

    if not limit.period:
        return is_limit_triggered, triggers_data

    start_date: datetime.datetime = _get_start_date_of_limit(
        trx.created_at,
        limit.period,
    )
    end_date: datetime.datetime = trx.created_at

    transactions_for_period: list[CustomerLimitTransactionData] = list(
        PaymentTransaction.objects.filter(
            customer=limit.customer,
            status__in=(
                const.TransactionStatus.SUCCESS,
                const.TransactionStatus.FAILED,
            ),
            created_at__gte=start_date,
            created_at__lte=end_date,
        ).values("status", "amount")
    )

    if limit.max_successful_operations:
        successful_transactions_count = len(
            [
                transaction
                for transaction in transactions_for_period
                if transaction["status"] == const.TransactionStatus.SUCCESS
            ]
        )
        if successful_transactions_count >= limit.max_successful_operations:
            is_limit_triggered = True
            triggers_data["max_successful_operations"] = (
                f"Number of successful transactions {successful_transactions_count} has exceeded "
                f"limit {limit.max_successful_operations}"
            )

    if limit.max_failed_operations:
        current_failed_transactions_count = len(
            [
                transaction
                for transaction in transactions_for_period
                if transaction["status"] == const.TransactionStatus.FAILED
            ]
        )
        if current_failed_transactions_count >= limit.max_failed_operations:
            is_limit_triggered = True
            triggers_data["max_failed_operations"] = (
                f"Number of failed transactions {current_failed_transactions_count} has exceeded "
                f"limit {limit.max_failed_operations}"
            )

    if limit.total_successful_amount:
        current_successful_transactions_amount = sum(
            transaction["amount"]
            for transaction in transactions_for_period
            if transaction["status"] == const.TransactionStatus.SUCCESS
        )
        if (
            current_successful_transactions_amount + trx.amount
            > limit.total_successful_amount
        ):
            is_limit_triggered = True
            triggers_data["total_successful_amount"] = (
                f"Total successful amount {current_successful_transactions_amount} with current "
                f"transaction amount {trx.amount} is greater than limit {limit.total_successful_amount}"
            )

    return is_limit_triggered, triggers_data


def _check_merchant_limit(
    limit: limit_models.MerchantLimit,
    trx: PaymentTransaction,
) -> tuple[bool, dict[str, str]]:
    logger.info(
        "Checking merchant limit",
        extra={
            "type": limit.limit_type,
            "scope": limit.scope,
            "merchant": limit.merchant,
            "wallet": limit.wallet,
            "trx_id": trx.id,
            "limit_id": limit.id,
        },
    )
    is_limit_triggered = False
    triggers_data: dict[str, str] = {}

    if limit.limit_type == limit_models.LimitType.MIN_AMOUNT_SINGLE_OPERATION and (
        (
            limit.scope == limit_models.MerchantLimitScope.MERCHANT
            and trx.wallet.wallet.merchant == limit.merchant
        )
        or (
            limit.scope == limit_models.MerchantLimitScope.WALLET
            and trx.wallet.wallet == limit.wallet
        )
    ):
        assert limit.min_amount is not None

        if trx.amount < limit.min_amount:
            is_limit_triggered = True
            triggers_data[
                limit_models.LimitType.MIN_AMOUNT_SINGLE_OPERATION.label
            ] = f"Transaction amount {trx.amount} is less than limit {limit.min_amount}"
            triggers_data["scope"] = limit.scope

    if limit.limit_type == limit_models.LimitType.MAX_AMOUNT_SINGLE_OPERATION and (
        (
            limit.scope == limit_models.MerchantLimitScope.MERCHANT
            and trx.wallet.wallet.merchant == limit.merchant
        )
        or (
            limit.scope == limit_models.MerchantLimitScope.WALLET
            and trx.wallet.wallet == limit.wallet
        )
    ):
        assert limit.max_amount is not None

        if trx.amount > limit.max_amount:
            is_limit_triggered = True
            triggers_data[
                limit_models.LimitType.MAX_AMOUNT_SINGLE_OPERATION.label
            ] = f"Transaction amount {trx.amount} is greater than limit {limit.max_amount}"
            triggers_data["scope"] = limit.scope

    if limit.limit_type == limit_models.LimitType.MAX_OPERATIONS_BURST:
        assert limit.burst_minutes is not None
        assert limit.max_operations is not None

        window_start = trx.created_at - datetime.timedelta(minutes=limit.burst_minutes)
        burst_qs = PaymentTransaction.objects.filter(
            created_at__gt=window_start,
            created_at__lte=trx.created_at,
        )
        if limit.scope == limit_models.MerchantLimitScope.MERCHANT:
            assert limit.merchant_id is not None
            burst_qs = burst_qs.filter(wallet__wallet__merchant_id=limit.merchant_id)
        elif limit.scope == limit_models.MerchantLimitScope.WALLET:
            assert limit.wallet_id is not None
            burst_qs = burst_qs.filter(wallet__wallet_id=limit.wallet_id)
        else:
            raise ValueError(f"Invalid scope: {limit.scope}")  # pragma: no cover
        operations_count = burst_qs.count()

        if operations_count > limit.max_operations:
            is_limit_triggered = True
            triggers_data[limit_models.LimitType.MAX_OPERATIONS_BURST.label] = (
                f"Operations count {operations_count} is greater than limit {limit.max_operations} "
                f"for period {limit.burst_minutes} minutes"
            )

    if not limit.period:
        return is_limit_triggered, triggers_data

    start_date: datetime.datetime = _get_start_date_of_limit(
        trx.created_at, limit.period
    )
    end_date: datetime.datetime = trx.created_at

    transactions_for_period_query = PaymentTransaction.objects.filter(
        status__in=(
            const.TransactionStatus.SUCCESS,
            const.TransactionStatus.FAILED,
        ),
        created_at__gte=start_date,
        created_at__lte=end_date,
    )

    if limit.scope == limit_models.MerchantLimitScope.MERCHANT:
        assert limit.merchant_id is not None
        transactions_for_period_query = transactions_for_period_query.select_related(
            "wallet__wallet",
        ).filter(wallet__wallet__merchant_id=limit.merchant_id)
    elif limit.scope == limit_models.MerchantLimitScope.WALLET:
        assert limit.wallet_id is not None
        transactions_for_period_query = transactions_for_period_query.select_related(
            "wallet",
        ).filter(wallet__wallet_id=limit.wallet_id)
    else:
        raise ValueError(f"Invalid scope: {limit.scope}")  # pragma: no cover

    transactions_for_period: list[MerchantLimitTransactionData] = list(
        transactions_for_period_query.values("status", "amount", "type", "created_at")
    )

    if limit.limit_type == limit_models.LimitType.MAX_SUCCESSFUL_DEPOSITS:
        assert limit.max_operations is not None

        successful_deposits_count = len(
            [
                transaction
                for transaction in transactions_for_period
                if transaction["status"] == const.TransactionStatus.SUCCESS
                and transaction["type"] == const.TransactionType.DEPOSIT
            ]
        )
        if successful_deposits_count >= limit.max_operations:
            is_limit_triggered = True
            triggers_data[limit_models.LimitType.MAX_SUCCESSFUL_DEPOSITS.label] = (
                f"Number of successful deposits {successful_deposits_count} has exceeded "
                f"limit {limit.max_operations}"
            )

    if limit.limit_type == limit_models.LimitType.MAX_OVERALL_DECLINE_PERCENT:
        assert limit.max_overall_decline_percent is not None

        total_transactions_count: int = len(
            [
                transaction
                for transaction in transactions_for_period
                if transaction["status"]
                in {const.TransactionStatus.SUCCESS, const.TransactionStatus.FAILED}
            ]
        )
        failed_transactions_count: int = len(
            [
                transaction
                for transaction in transactions_for_period
                if transaction["status"] == const.TransactionStatus.FAILED
            ]
        )
        failed_withdrawals_percent: Decimal = round(
            Decimal(failed_transactions_count) / Decimal(total_transactions_count) * 100
            if total_transactions_count
            else Decimal(0),
            ndigits=2,
        )
        if failed_withdrawals_percent > limit.max_overall_decline_percent:
            is_limit_triggered = True
            triggers_data[limit_models.LimitType.MAX_OVERALL_DECLINE_PERCENT.label] = (
                f"Failed transactions percent {failed_withdrawals_percent} is greater than "
                f"limit {limit.max_overall_decline_percent}"
            )

    if limit.limit_type == limit_models.LimitType.MAX_WITHDRAWAL_DECLINE_PERCENT:
        assert limit.max_withdrawal_decline_percent is not None

        total_withdrawals_count: int = len(
            [
                transaction
                for transaction in transactions_for_period
                if transaction["type"] == const.TransactionType.WITHDRAWAL
                and transaction["status"]
                in {const.TransactionStatus.SUCCESS, const.TransactionStatus.FAILED}
            ]
        )
        failed_withdrawals_count: int = len(
            [
                transaction
                for transaction in transactions_for_period
                if transaction["status"] == const.TransactionStatus.FAILED
                and transaction["type"] == const.TransactionType.WITHDRAWAL
            ]
        )
        failed_withdrawals_percent = round(
            Decimal(failed_withdrawals_count) / Decimal(total_withdrawals_count) * 100
            if total_withdrawals_count
            else Decimal(0),
            ndigits=2,
        )
        if failed_withdrawals_percent > limit.max_withdrawal_decline_percent:
            is_limit_triggered = True
            triggers_data[
                limit_models.LimitType.MAX_WITHDRAWAL_DECLINE_PERCENT.label
            ] = (
                f"Failed withdrawals percent {failed_withdrawals_percent} is greater than "
                f"limit {limit.max_withdrawal_decline_percent}"
            )

    if limit.limit_type == limit_models.LimitType.MAX_DEPOSIT_DECLINE_PERCENT:
        assert limit.max_deposit_decline_percent is not None

        total_deposits_count: int = len(
            [
                transaction
                for transaction in transactions_for_period
                if transaction["type"] == const.TransactionType.DEPOSIT
                and transaction["status"]
                in {const.TransactionStatus.SUCCESS, const.TransactionStatus.FAILED}
            ]
        )
        failed_deposits_count: int = len(
            [
                transaction
                for transaction in transactions_for_period
                if transaction["status"] == const.TransactionStatus.FAILED
                and transaction["type"] == const.TransactionType.DEPOSIT
            ]
        )
        failed_deposits_percent: Decimal = round(
            Decimal(failed_deposits_count) / Decimal(total_deposits_count) * 100
            if total_deposits_count
            else Decimal(0),
            ndigits=2,
        )
        if failed_deposits_percent > limit.max_deposit_decline_percent:
            is_limit_triggered = True
            triggers_data[limit_models.LimitType.MAX_DEPOSIT_DECLINE_PERCENT.label] = (
                f"Failed deposits percent {failed_deposits_percent} is greater than "
                f"limit {limit.max_deposit_decline_percent}"
            )

    if (
        limit.limit_type == limit_models.LimitType.TOTAL_AMOUNT_DEPOSITS_PERIOD
        and trx.type == const.TransactionType.DEPOSIT
    ):
        assert limit.total_amount is not None

        successful_deposits_amount = sum(
            transaction["amount"]
            for transaction in transactions_for_period
            if transaction["type"] == const.TransactionType.DEPOSIT
        )
        if successful_deposits_amount + trx.amount > limit.total_amount:
            is_limit_triggered = True
            triggers_data[limit_models.LimitType.TOTAL_AMOUNT_DEPOSITS_PERIOD.label] = (
                f"Total successful deposits amount {successful_deposits_amount} with current transaction "
                f"amount {trx.amount} is greater than limit {limit.total_amount} for period {limit.period}"
            )

    if (
        limit.limit_type == limit_models.LimitType.TOTAL_AMOUNT_WITHDRAWALS_PERIOD
        and trx.type == const.TransactionType.WITHDRAWAL
    ):
        assert limit.total_amount is not None

        successful_withdrawals_amount = sum(
            transaction["amount"]
            for transaction in transactions_for_period
            if transaction["type"] == const.TransactionType.WITHDRAWAL
        )
        if successful_withdrawals_amount + trx.amount > limit.total_amount:
            is_limit_triggered = True
            triggers_data[
                limit_models.LimitType.TOTAL_AMOUNT_WITHDRAWALS_PERIOD.label
            ] = (
                "Total successful withdrawals amount {0} with current transaction "
                "amount {1} is greater than limit {2} for period {3}"
            ).format(
                successful_withdrawals_amount,
                trx.amount,
                limit.total_amount,
                limit.period,
            )

    if limit.limit_type == limit_models.LimitType.MAX_WITHDRAWAL_TO_DEPOSIT_RATIO:
        assert limit.max_ratio is not None

        withdrawals_transactions_amount = sum(
            transaction["amount"]
            for transaction in transactions_for_period
            if transaction["type"] == const.TransactionType.WITHDRAWAL
        )
        deposits_transactions_amount = sum(
            transaction["amount"]
            for transaction in transactions_for_period
            if transaction["type"] == const.TransactionType.DEPOSIT
        )
        if withdrawals_transactions_amount == 0:
            current_ratio: Decimal = Decimal(0)
        elif deposits_transactions_amount == 0:
            current_ratio = Decimal(100)
        else:
            current_ratio = round(
                Decimal(withdrawals_transactions_amount / deposits_transactions_amount)
                * 100,
                ndigits=2,
            )
        if current_ratio > limit.max_ratio:
            is_limit_triggered = True
            triggers_data[
                limit_models.LimitType.MAX_WITHDRAWAL_TO_DEPOSIT_RATIO.label
            ] = (
                f"Withdrawals to deposits ratio {current_ratio} is greater than "
                f"limit {limit.max_ratio}"
            )

    if is_limit_triggered:
        triggers_data["scope"] = limit.scope
        logger.info(
            "Limit triggered",
            extra={
                "transaction_id": trx.id,
                "limit_id": limit.id,
                "limit_type": limit.limit_type,
                "limit_category": limit.category,
                "triggers_data": triggers_data,
            },
        )
    else:
        logger.info(
            "Limit not triggered",
            extra={
                "transaction_id": trx.id,
                "limit_id": limit.id,
                "limit_type": limit.limit_type,
                "limit_category": limit.category,
            },
        )

    return is_limit_triggered, triggers_data


def _get_start_date_of_limit(
    trx_created_at: datetime.datetime,
    period: LimitPeriod | str,
) -> datetime.datetime:
    if period == LimitPeriod.ONE_HOUR:
        return trx_created_at - datetime.timedelta(hours=1)
    elif period == LimitPeriod.TWENTY_FOUR_HOURS:
        return trx_created_at - datetime.timedelta(hours=24)
    elif period == LimitPeriod.BEGINNING_OF_HOUR:
        # start of the current hour (e.g., 21:47:00 -> 21:00:00)
        return trx_created_at.replace(minute=0, second=0, microsecond=0)
    elif period == LimitPeriod.BEGINNING_OF_DAY:
        # start of the current day (e.g., 21:47:00 -> 00:00:00)
        return trx_created_at.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Invalid period: {period}")  # pragma: no cover


def _resolve_customer_and_merchant_limit_conflicts(
    limits: list[limit_models.CustomerLimit | limit_models.MerchantLimit],
) -> tuple[
    list[limit_models.CustomerLimit | limit_models.MerchantLimit],
    list[tuple[limit_models.MerchantLimit, str]],
]:
    # NOTE: CustomerLimit overrides MerchantLimit if they are both of the same type
    customer_min_operation_limit_exists: bool = any(
        limit
        for limit in limits
        if isinstance(limit, limit_models.CustomerLimit) and limit.min_operation_amount
    )
    customer_max_operation_limit_exists: bool = any(
        limit
        for limit in limits
        if isinstance(limit, limit_models.CustomerLimit) and limit.max_operation_amount
    )

    removed_limits_with_reasons: list[tuple[limit_models.MerchantLimit, str]] = []

    if customer_min_operation_limit_exists:
        to_remove_min: list[limit_models.MerchantLimit] = [
            limit
            for limit in limits
            if isinstance(limit, limit_models.MerchantLimit)
            and limit.limit_type == limit_const.LimitType.MIN_AMOUNT_SINGLE_OPERATION
        ]
        if to_remove_min:
            for lim in to_remove_min:
                removed_limits_with_reasons.append(
                    (lim, "overridden by customer min_operation_amount limit")
                )
        limits = [limit for limit in limits if limit not in to_remove_min]
    if customer_max_operation_limit_exists:
        to_remove_max: list[limit_models.MerchantLimit] = [
            limit
            for limit in limits
            if isinstance(limit, limit_models.MerchantLimit)
            and limit.limit_type == limit_const.LimitType.MAX_AMOUNT_SINGLE_OPERATION
        ]
        if to_remove_max:
            for lim in to_remove_max:
                removed_limits_with_reasons.append(
                    (lim, "overridden by customer max_operation_amount limit")
                )
        limits = [limit for limit in limits if limit not in to_remove_max]

    return limits, removed_limits_with_reasons


def _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
    limits: list[limit_models.CustomerLimit | limit_models.MerchantLimit],
) -> tuple[
    list[limit_models.CustomerLimit | limit_models.MerchantLimit],
    list[tuple[limit_models.MerchantLimit, str]],
]:
    # NOTE: RiskMerchantLimit overrides GlobalRiskMerchantLimit if they are both of the same type
    removed_limits_with_reasons: list[tuple[limit_models.MerchantLimit, str]] = []
    wallet_limits: list[limit_models.MerchantLimit] = [
        limit
        for limit in limits
        if isinstance(limit, limit_models.MerchantLimit)
        and limit.scope == limit_models.MerchantLimitScope.WALLET
    ]
    risk_merchant_limit_types: list[str] = [
        limit.limit_type
        for limit in wallet_limits
        if limit.category == LimitCategory.RISK
    ]
    for limit in wallet_limits:
        if (
            limit.category == LimitCategory.GLOBAL_RISK
            and limit.limit_type in risk_merchant_limit_types
        ):
            removed_limits_with_reasons.append(
                (limit, f"overridden by risk limit of same type ({limit.limit_type})")
            )

    filtered_limits = limits
    if removed_limits_with_reasons:
        limits_to_remove = [limit for limit, _ in removed_limits_with_reasons]
        filtered_limits = [limit for limit in limits if limit not in limits_to_remove]

    return filtered_limits, removed_limits_with_reasons


def _notify_about_alerts(alerts: list[limit_models.LimitAlert]) -> None:
    alerts_by_channel: dict[str, list[limit_models.LimitAlert]] = defaultdict(list)

    for alert in alerts:
        limit = alert.customer_limit or alert.merchant_limit
        if limit and limit.slack_channel_override:
            channel = limit.slack_channel_override
        elif alert.is_critical:
            channel = SLACK_CHANNEL_NAME_CRITICAL_LIMITS
        else:
            channel = SLACK_CHANNEL_NAME_REGULAR_LIMITS
        alerts_by_channel[channel].append(alert)

    for channel, channel_alerts in alerts_by_channel.items():
        if not channel_alerts:
            continue
        message = construct_notification_message(channel_alerts)
        alert_ids = [alert.id for alert in channel_alerts]
        limit_models.LimitAlert.objects.filter(id__in=alert_ids).update(
            notification_text=message,
        )
        notify_in_slack.apply_async(
            kwargs={
                "message": message,
                "channel": channel,
                "alert_ids": alert_ids,
            }
        )
