from auditlog.models import AuditlogHistoryField
from django.db import models
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.limits.const import LimitPeriod


class LimitCategory(models.TextChoices):
    RISK = "risk", "Risk"
    GLOBAL_RISK = "global_risk", "Global Risk"
    BUSINESS = "business", "Business"


class BaseLimit(BaseDjangoModel):
    active = models.BooleanField(
        default=True, help_text="Status of the limit: enabled or disabled",
    )
    description = models.TextField(
        blank=True, help_text="User-defined limit description",
    )
    category = models.CharField(max_length=50, choices=LimitCategory.choices)
    period = models.CharField(
        max_length=255,
        choices=LimitPeriod.choices,
        null=True,
        blank=True,
    )
    notification_groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="%(class)s_limits_to_notify",
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

    class Meta:
        abstract = True
