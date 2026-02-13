from django.conf import settings
from django.db.models import TextChoices




class LimitType(TextChoices):
    MAX_SUCCESSFUL_DEPOSITS = (
        "max_successful_deposits",
        "Максимальное количество успешных депозитов за период",
    )
    MAX_OVERALL_DECLINE_PERCENT = (
        "max_overall_decline_percent",
        "Максимальный процент деклайнов за период",
    )
    MAX_WITHDRAWAL_DECLINE_PERCENT = (
        "max_withdrawal_decline_percent",
        "Максимальный процент деклайнов выплат за период",
    )
    MAX_DEPOSIT_DECLINE_PERCENT = (
        "max_deposit_decline_percent",
        "Максимальный процент деклайнов депозитов за период",
    )
    MIN_AMOUNT_SINGLE_OPERATION = (
        "min_amount_single_operation",
        "Минимальная сумма одной операции",
    )
    MAX_AMOUNT_SINGLE_OPERATION = (
        "max_amount_single_operation",
        "Максимальная сумма одной операции",
    )
    TOTAL_AMOUNT_DEPOSITS_PERIOD = (
        "total_amount_deposits_period",
        "Общая сумма депозитов за период",
    )
    TOTAL_AMOUNT_WITHDRAWALS_PERIOD = (
        "total_amount_withdrawals_period",
        "Общая сумма выплат за период",
    )
    MAX_WITHDRAWAL_TO_DEPOSIT_RATIO = (
        "max_withdrawal_to_deposit_ratio",
        "Максимальный процент выплат к депозитам за период",
    )
    MAX_OPERATIONS_BURST = (
        "max_operations_burst",
        "Максимальное количество любых операций за короткий период",
    )


class LimitPeriod(TextChoices):
    ONE_HOUR = "1h", "1 Hour"
    TWENTY_FOUR_HOURS = "24h", "24 Hours"
    BEGINNING_OF_HOUR = "beginning_of_hour", "Beginning of Hour"
    BEGINNING_OF_DAY = "beginning_of_day", "Beginning of Day"


if settings.IS_PRODUCTION:
    SLACK_CHANNEL_NAME_REGULAR_LIMITS = "#rozert_pay-limit_alerts-regular"
    SLACK_CHANNEL_NAME_CRITICAL_LIMITS = "#rozert_pay-limit_alerts-critical"
else:
    SLACK_CHANNEL_NAME_REGULAR_LIMITS = "#rozert_pay-limit_alerts-regular-dev"
    SLACK_CHANNEL_NAME_CRITICAL_LIMITS = "#rozert_pay-limit_alerts-critical-dev"


REGULAR_LIMIT_COLOR = "#b8860b"
CRITICAL_LIMIT_COLOR = "#dc3545"

COLOR_OF_INACTIVE_STATUS = "#6c757d"
COLOR_OF_ACTIVE_STATUS = "#198754"
