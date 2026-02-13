from django.http import HttpRequest, HttpResponse
from rozert_pay.feature_flags.services import update_feature_flag_status
from rozert_pay.feature_flags.const import FeatureFlagName
from django.utils.translation import gettext_lazy as _
from django.contrib import messages


class RiskControlActionsMixin:
    changelist_actions = ("enable_risk_control", "disable_risk_control")

    def enable_risk_control(self, request: HttpRequest, obj=None) -> HttpResponse:
        update_feature_flag_status(
            name=FeatureFlagName.RISK_CONTROL_ENABLED,
            status=True,
        )
        messages.success(request, _("Risk control enabled successfully."))
        return HttpResponse()

    enable_risk_control.label = _("Enable Risk control")
    enable_risk_control.short_description = _("Enable Risk control")

    def disable_risk_control(self, request: HttpRequest, obj=None) -> HttpResponse:
        update_feature_flag_status(
            name=FeatureFlagName.RISK_CONTROL_ENABLED,
            status=False,
        )
        messages.success(request, _("Risk control disabled successfully."))
        return HttpResponse()

    disable_risk_control.label = _("Disable Risk control")
    disable_risk_control.short_description = _("Disable Risk control")
