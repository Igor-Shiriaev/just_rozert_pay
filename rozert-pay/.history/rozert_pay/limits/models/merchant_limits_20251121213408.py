from typing import Optional

from auditlog.models import AuditlogHistoryField
from auditlog.registry import auditlog
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.limits.const import LimitPeriod, LimitType
from rozert_pay.limits.models.common import LimitCategory
from rozert_pay.payment.models import Merchant, Wallet


class MerchantLimitScope(models.TextChoices):
    MERCHANT = "merchant", "Merchant"
    WALLET = "wallet", "Merchant Wallet"


class MerchantLimit(BaseDjangoModel):
    merchant_id: int | None
    wallet_id: int | None

    active = models.BooleanField(
        default=True, help_text="Status of the limit: enabled or disabled"
    )
    description = models.TextField(
        blank=True, help_text="User-defined limit description"
    )

    scope = models.CharField(max_length=50, choices=MerchantLimitScope.choices)
    merchant: Optional[Merchant] = models.ForeignKey(  # type: ignore[assignment]
        to="payment.Merchant",
        on_delete=models.CASCADE,
        related_name="merchant_limits",
        verbose_name="Merchant",
        null=True,
        blank=True,
    )

    wallet: Optional[Wallet] = models.ForeignKey(  # type: ignore[assignment]
        to="payment.Wallet",
        on_delete=models.CASCADE,
        related_name="merchant_limits",
        verbose_name="Wallet",
        null=True,
        blank=True,
    )
    category = models.CharField(max_length=50, choices=LimitCategory.choices)
    limit_type = models.CharField(max_length=50, choices=LimitType.choices)
    period = models.CharField(
        max_length=20,
        choices=LimitPeriod.choices,
        null=True,
        blank=True,
    )

    max_operations = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Maximum number of operations",
    )
    max_overall_decline_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Max Overall Decline %",
    )
    max_withdrawal_decline_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Max Withdrawal Decline %",
    )
    max_deposit_decline_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Max Deposit Decline %",
    )
    min_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Minimum amount",
    )
    max_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Maximum amount",
    )
    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Total amount per period",
    )
    max_ratio = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Max Ratio %",
    )
    burst_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Number of minutes for checking operation bursts",
    )

    notification_groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="merchant_limits_to_notify",
        help_text="User groups that will receive notifications about this alert.",
    )
    slack_channel_override = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Override the default Slack channel for notifications.",
    )

    decline_on_exceed = models.BooleanField(
        default=False, help_text="Decline operation if limit is exceeded"
    )
    is_critical = models.BooleanField(
        default=False, help_text="Escalate alert to critical notifications category"
    )
    history = AuditlogHistoryField(delete_related=True)

    def __str__(self) -> str:
        return (
            f"MerchantLimit(id={self.id}, type={self.limit_type}, scope={self.scope})"
        )

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}

        duplicate_limit_query = MerchantLimit.objects.filter(
            active=True,
            limit_type=self.limit_type,
            period=self.period,
            wallet_id=self.wallet_id,  # type: ignore[misc]
            merchant_id=self.merchant_id,  # type: ignore[misc]
            scope=self.scope,
        )
        if self.pk:
            duplicate_limit_query = duplicate_limit_query.exclude(pk=self.pk)
        if duplicate_limit_query.exists():
            errors.setdefault(NON_FIELD_ERRORS, []).append(
                "An active limit with the same type, period, scope and merchant/wallet already exists"
            )

        if not any(
            [
                self.max_operations,
                self.max_overall_decline_percent,
                self.max_withdrawal_decline_percent,
                self.max_deposit_decline_percent,
                self.min_amount,
                self.max_amount,
                self.total_amount,
                self.max_ratio,
                self.burst_minutes,
            ]
        ):
            errors.setdefault(NON_FIELD_ERRORS, []).append(
                "At least one limit parameter must be set"
            )

        if self.merchant and self.wallet:
            errors.setdefault("merchant", []).append(
                "Merchant and wallet cannot be set at the same time"
            )
            errors.setdefault("wallet", []).append(
                "Merchant and wallet cannot be set at the same time"
            )

        if self.scope == MerchantLimitScope.MERCHANT and not self.merchant:
            errors.setdefault("merchant", []).append(
                "Merchant is required for merchant scope"
            )
        if self.scope == MerchantLimitScope.WALLET and not self.wallet:
            errors.setdefault("wallet", []).append(
                "Wallet is required for wallet scope"
            )

        if (
            self.limit_type == LimitType.MAX_WITHDRAWAL_TO_DEPOSIT_RATIO
            and not self.max_ratio
        ):
            errors.setdefault("max_ratio", []).append(
                "Max ratio is required for max withdrawal to deposit ratio limit"
            )

        if (
            self.limit_type == LimitType.MAX_OPERATIONS_BURST
            and self.scope != MerchantLimitScope.MERCHANT
        ):
            errors.setdefault("scope", []).append(
                "Scope must be 'merchant' for max operations burst limit"
            )

        if (
            self.limit_type
            in {
                LimitType.TOTAL_AMOUNT_WITHDRAWALS_PERIOD,
                LimitType.TOTAL_AMOUNT_DEPOSITS_PERIOD,
            }
            and self.total_amount is None
        ):
            errors.setdefault("total_amount", []).append(
                "Total amount is required for total amount withdrawals or deposits period limit"
            )

        if self.limit_type == LimitType.MAX_OPERATIONS_BURST:
            if not self.burst_minutes:
                errors.setdefault("burst_minutes", []).append(
                    "Burst minutes are required for max operations burst limit"
                )
            if not self.max_operations:
                errors.setdefault("max_operations", []).append(
                    "Max operations are required for max operations burst limit"
                )

        if (
            any(
                [
                    self.max_overall_decline_percent,
                    self.max_withdrawal_decline_percent,
                    self.max_deposit_decline_percent,
                    self.total_amount,
                    self.max_ratio,
                ]
            )
            and not self.period
        ):
            errors.setdefault("period", []).append(
                "Period is required for this type of limit"
            )
        if (
            self.category == LimitCategory.GLOBAL_RISK
            and self.scope != MerchantLimitScope.WALLET
            or not self.wallet
        ):
            errors.setdefault("category", []).append(
                "Scope must be 'wallet' for global risk limit and wallet must be set"
            )

        if errors:
            raise ValidationError(errors)


auditlog.register(MerchantLimit, serialize_data=True)


class RiskMerchantLimitManager(models.Manager["MerchantLimit"]):
    def get_queryset(self) -> models.QuerySet["MerchantLimit"]:
        return super().get_queryset().filter(category=LimitCategory.RISK)


class BusinessMerchantLimitManager(models.Manager["MerchantLimit"]):
    def get_queryset(self) -> models.QuerySet["MerchantLimit"]:
        return super().get_queryset().filter(category=LimitCategory.BUSINESS)


class RiskMerchantLimit(MerchantLimit):
    objects: models.Manager["RiskMerchantLimit"] = RiskMerchantLimitManager()  # type: ignore[misc, assignment]

    class Meta:
        proxy = True
        verbose_name = "Risk Merchant Limit"
        verbose_name_plural = "Risk Merchant Limits"


class BusinessMerchantLimit(MerchantLimit):
    objects: models.Manager["BusinessMerchantLimit"] = BusinessMerchantLimitManager()  # type: ignore[misc, assignment]

    class Meta:
        proxy = True
        verbose_name = "Business Merchant Limit"
        verbose_name_plural = "Business Merchant Limits"

class 