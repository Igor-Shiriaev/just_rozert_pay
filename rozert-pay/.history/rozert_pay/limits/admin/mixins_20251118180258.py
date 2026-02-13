from django.http import HttpRequest
from django.db.models import QuerySet
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.feature_flags.services import update_feature_flag_status
from rozert_pay.feature_flags.const import FeatureFlagName
from django.utils.translation import gettext_lazy as _


class RiskControlMixin:
    def enable_risk_control(self: ModelAdmin, request: HttpRequest, queryset: QuerySet[CustomerLimit]) -> None:
        update_feature_flag_status(name=FeatureFlagName.RISK_CONTROL_ENABLED, status=True)
        self.message_user(request, _("Risk control enabled successfully."))

    def disable_risk_control(self, request: HttpRequest, queryset: QuerySet[CustomerLimit]) -> None:
        update_feature_flag_status(name=FeatureFlagName.RISK_CONTROL_ENABLED, status=False)
        self.message_user(request, _("Risk control disabled successfully."))