from typing import Optional

from auditlog.models import AuditlogHistoryField
from auditlog.registry import auditlog
from django.core.exceptions import ValidationError
from django.db import models
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.limits.models.customer_limits import (  # pylint: disable=forbidden-import
    CustomerLimit,
)
from rozert_pay.limits.models.merchant_limits import (  # pylint: disable=forbidden-import
    MerchantLimit,
)


class LimitAlert(BaseDjangoModel):
    customer_limit: Optional[CustomerLimit] = models.ForeignKey(  # type: ignore[assignment]
        to="limits.CustomerLimit",
        on_delete=models.CASCADE,
        related_name="limit_trigger_logs",
        verbose_name="Customer Limit",
        null=True,
        blank=True,
    )
    merchant_limit: Optional[MerchantLimit] = models.ForeignKey(  # type: ignore[assignment]
        to="limits.MerchantLimit",
        on_delete=models.CASCADE,
        related_name="limit_trigger_logs",
        verbose_name="Merchant Limit",
        null=True,
        blank=True,
    )
    transaction = models.ForeignKey(
        to="payment.PaymentTransaction",
        on_delete=models.CASCADE,
        related_name="limit_trigger_logs",
        verbose_name="Transaction",
        help_text="Transaction that triggered the limit",
    )
    is_active = models.BooleanField(default=True)
    is_notified = models.BooleanField(
        default=False,
        verbose_name="Notification sent to Slack",
        help_text="Indicates whether a notification was sent to Slack",
    )
    acknowledged_by = models.ManyToManyField(
        "account.User",
        blank=True,
        related_name="acknowledged_alerts",
        verbose_name="Acknowledged by",
    )
    notification_text = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notification text",
        help_text="Notification text sent to Slack",
    )
    extra = models.JSONField(default=dict)
    notification_groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="alerts_to_notify",
        verbose_name="Notification Groups",
    )
    history = AuditlogHistoryField(delete_related=True)

    @property
    def is_critical(self) -> bool:
        return bool(
            (self.customer_limit and self.customer_limit.is_critical)
            or (self.merchant_limit and self.merchant_limit.is_critical)
        )

    def clean(self) -> None:
        super().clean()
        if not self.customer_limit and not self.merchant_limit:
            raise ValidationError("Customer or merchant limit must be set")
        if self.customer_limit and self.merchant_limit:
            raise ValidationError(
                "Customer and merchant limits cannot be set at the same time"
            )
        if not self.extra:
            raise ValidationError("Extra data must be set")


auditlog.register(LimitAlert, serialize_data=True)
