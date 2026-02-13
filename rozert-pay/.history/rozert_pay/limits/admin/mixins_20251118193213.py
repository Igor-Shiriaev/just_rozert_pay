from typing import Any, Iterable
from django.http import HttpRequest, HttpResponseRedirect
from rozert_pay.feature_flags.services import update_feature_flag_status
from rozert_pay.feature_flags.const import FeatureFlagName
from django.utils.translation import gettext_lazy as _
from django.contrib import messages


class RiskControlActionsMixin:
    changelist_actions: Iterable[str] = ("enable_risk_control", "disable_risk_control")

    def get_changelist_actions(self, request: HttpRequest) -> Iterable[str]:
        actions = list(super().get_changelist_actions(request))  # type: ignore[misc]
        for action in self.changelist_actions:
            if action not in actions:
                actions.append(action)
        return actions

    def enable_risk_control(self, request: HttpRequest, queryset=None) -> HttpResponseRedirect:
        update_feature_flag_status(
            name=FeatureFlagName.RISK_CONTROL_ENABLED,
            status=True,
        )
        messages.success(request, _("Risk control enabled successfully."))
        return None

    enable_risk_control.label = _("Enable Risk control")  # type: ignore[attr-defined]
    enable_risk_control.short_description = _("Enable Risk control")  # type: ignore[attr-defined]

    def disable_risk_control(self, request: HttpRequest, queryset=None) -> HttpResponseRedirect:
        update_feature_flag_status(
            name=FeatureFlagName.RISK_CONTROL_ENABLED,
            status=False,
        )
        messages.success(request, _("Risk control disabled successfully."))
        return None

    disable_risk_control.label = _("Disable Risk control")  # type: ignore[attr-defined]
    # disable_risk_control.short_description = _("Disable Risk control")  # type: ignore[attr-defined]
