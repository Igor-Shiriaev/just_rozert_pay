from decimal import Decimal
from typing import Any

from auditlog.models import AuditlogHistoryField
from auditlog.registry import auditlog
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.limits import const as limit_const
from rozert_pay.limits.const import LimitPeriod
from rozert_pay.limits.models.common import LimitCategory


class CustomerLimit(BaseDjangoModel):
    customer_id: int

    customer = models.ForeignKey(
        "payment.Customer",
        on_delete=models.CASCADE,
        related_name="client_limits",
        verbose_name="Client",
        null=False,
        blank=False,
    )
    category = models.CharField(max_length=50, choices=LimitCategory.choices)
    active = models.BooleanField(
        default=True, help_text="Limit status, enabled or disabled"
    )
    description = models.TextField(
        blank=True, help_text="Limit description set by the user"
    )

    period = models.CharField(
        max_length=255,
        choices=LimitPeriod.choices,
        null=True,
        blank=True,
    )

    max_successful_operations = models.PositiveIntegerField(
        verbose_name="Maximum number of successful operations per period",
        null=True,
        blank=True,
    )

    max_failed_operations = models.PositiveIntegerField(
        verbose_name="Maximum number of failed operations per period",
        null=True,
        blank=True,
    )

    min_operation_amount = models.DecimalField(
        verbose_name=limit_const.VERBOSE_NAME_MIN_AMOUNT_SINGLE_OPERATION,
        help_text="Minimum amount allowed for a single operation",
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        null=True,
        blank=True,
    )

    max_operation_amount = models.DecimalField(
        verbose_name=limit_const.VERBOSE_NAME_MAX_AMOUNT_SINGLE_OPERATION,
        help_text="Maximum amount allowed for a single operation",
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        null=True,
        blank=True,
    )

    total_successful_amount = models.DecimalField(
        verbose_name="Total amount of successful operations per period",
        help_text="Maximum total amount of all successful operations for the specified period",
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        null=True,
        blank=True,
    )

    notification_groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="customer_limits_to_notify",
        help_text="User groups that will receive notifications about this alert.",
    )
    slack_channel_override = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Override the default Slack channel for notifications.",
    )

    decline_on_exceed = models.BooleanField(
        verbose_name="Reject on limit exceed",
        help_text="Enable automatic rejection of operations that exceed the limit",
        default=False,
    )

    is_critical = models.BooleanField(
        verbose_name="Critical limit",
        help_text="Escalates the alert to a critical notification",
        default=False,
    )
    history = AuditlogHistoryField(delete_related=True)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[str]] = {}

        duplicate_limit_query = CustomerLimit.objects.filter(
            active=True,
            customer_id=self.customer_id,
            period=self.period,
            max_successful_operations=self.max_successful_operations,
            max_failed_operations=self.max_failed_operations,
            min_operation_amount=self.min_operation_amount,
            max_operation_amount=self.max_operation_amount,
            total_successful_amount=self.total_successful_amount,
        )
        if self.pk:
            duplicate_limit_query = duplicate_limit_query.exclude(pk=self.pk)
        if duplicate_limit_query.exists():
            errors.setdefault(NON_FIELD_ERRORS, []).append(
                "An active limit for this customer with this period already exists"
            )
        if not any(
            [
                self.max_successful_operations,
                self.max_failed_operations,
                self.min_operation_amount,
                self.max_operation_amount,
                self.total_successful_amount,
            ]
        ):
            errors.setdefault(NON_FIELD_ERRORS, []).append(
                "At least one of the fields must be set"
            )

        if (
            any(
                [
                    self.max_successful_operations,
                    self.max_failed_operations,
                    self.total_successful_amount,
                ]
            )
            and not self.period
        ):
            errors.setdefault("period", []).append(
                "Period is required for this type of limit"
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        from rozert_pay.limits.services.limits import invalidate_limits_cache

        super().save(*args, **kwargs)
        invalidate_limits_cache()


auditlog.register(CustomerLimit, serialize_data=True)


class RiskCustomerLimit(CustomerLimit):

    class Meta:
        proxy = True
        verbose_name = "Risk Customer Limit"
        verbose_name_plural = "Risk Customer Limits"


class BusinessCustomerLimit(CustomerLimit):
    class Meta:
        proxy = True
        verbose_name = "Business Customer Limit"
        verbose_name_plural = "Business Customer Limits"
