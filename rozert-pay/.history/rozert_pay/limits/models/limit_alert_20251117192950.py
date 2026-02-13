from typing import Optional

from auditlog.models import AuditlogHistoryField
from auditlog.registry import auditlog
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit


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

    @property
    def limit_description(self) -> str:
        if self.customer_limit:
            return self.customer_limit.description or "Customer Limit"
        if self.merchant_limit:
            return self.merchant_limit.description or "Merchant Limit"
        return "N/A"

    @property
    def get_limit_admin_url(self) -> str:
        if self.customer_limit:
            if self.customer_limit.category == LimitCategory.RISK:
                return reverse(
                    "admin:limits_riskcustomerlimit_change", args=[self.customer_limit.pk]
                )
            else:
                return reverse(
                    "admin:limits_businesscustomerlimit_change", args=[self.customer_limit.pk]
                )
                "admin:limits_customerlimit_change", args=[self.customer_limit.pk]
            )
        if self.merchant_limit:
            return reverse(
                "admin:limits_merchantlimit_change", args=[self.merchant_limit.pk]
            )
        return "#"

    @property
    def get_transaction_admin_url(self) -> str:
        if self.transaction_id:
            return reverse(
                "admin:payment_paymenttransaction_change", args=[self.transaction_id]
            )
        return "#"

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
