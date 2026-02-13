from django.conf import settings
from django.db.models import TextChoices

VERBOSE_NAME_MIN_AMOUNT_SINGLE_OPERATION = "Minimum amount for a single operation"
VERBOSE_NAME_MAX_AMOUNT_SINGLE_OPERATION = "Maximum amount for a single operation"


class LimitType(TextChoices):
    MAX_SUCCESSFUL_DEPOSITS = (
        "max_successful_deposits",
        "Maximum number of successful deposits per period",
    )
    MAX_OVERALL_DECLINE_PERCENT = (
        "max_overall_decline_percent",
        "Maximum decline percentage per period",
    )
    MAX_WITHDRAWAL_DECLINE_PERCENT = (
        "max_withdrawal_decline_percent",
        "Maximum withdrawal decline percentage per period",
    )
    MAX_DEPOSIT_DECLINE_PERCENT = (
        "max_deposit_decline_percent",
        "Maximum deposit decline percentage per period",
    )
    MIN_AMOUNT_SINGLE_OPERATION = (
        "min_amount_single_operation",
        VERBOSE_NAME_MIN_AMOUNT_SINGLE_OPERATION,
    )
    MAX_AMOUNT_SINGLE_OPERATION = (
        "max_amount_single_operation",
        VERBOSE_NAME_MAX_AMOUNT_SINGLE_OPERATION,
    )
    TOTAL_AMOUNT_DEPOSITS_PERIOD = (
        "total_amount_deposits_period",
        "Total deposit amount per period",
    )
    TOTAL_AMOUNT_WITHDRAWALS_PERIOD = (
        "total_amount_withdrawals_period",
        "Total withdrawal amount per period",
    )
    MAX_WITHDRAWAL_TO_DEPOSIT_RATIO = (
        "max_withdrawal_to_deposit_ratio",
        "Maximum withdrawal-to-deposit ratio per period",
    )
    MAX_OPERATIONS_BURST = (
        "max_operations_burst",
        "Maximum number of any operations in a short period",
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

if settings.IS_PRODUCTION:
    SLACK_PS_STATUS_CHANNEL = "#ps-status"
else:
    SLACK_PS_STATUS_CHANNEL = "#ps-status-dev"


REGULAR_LIMIT_COLOR = "#b8860b"
CRITICAL_LIMIT_COLOR = "#dc3545"

COLOR_OF_INACTIVE_STATUS = "#6c757d"
COLOR_OF_ACTIVE_STATUS = "#198754"
