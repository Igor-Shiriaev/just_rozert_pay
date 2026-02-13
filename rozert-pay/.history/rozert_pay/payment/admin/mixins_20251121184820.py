from typing import Iterable

from django.contrib import messages
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _


class RiskControlActionsMixin:
    changelist_actions: Iterable[str] = ("enable_risk_control", "disable_risk_control")

    def enable_risk_control(self, request: HttpRequest, obj: Any) -> None:
        # obj is a single Article instance
        obj.risk_control = True
        obj.save()
        self.message_user(request, f'"{obj}" was published.')

    enable_risk_control.label = _("Enable Risk control")  # type: ignore[attr-defined]
    enable_risk_control.short_description = _("Enable Risk control")  # type: ignore[attr-defined]

    def disable_risk_control(self, request: HttpRequest, queryset=None) -> None:
        update_feature_flag_status(
            name=FeatureFlagName.RISK_CONTROL_ENABLED,
            status=False,
        )
        messages.success(request, _("Risk control disabled successfully."))
        return None

    disable_risk_control.label = _("Disable Risk control")  # type: ignore[attr-defined]
    disable_risk_control.short_description = _("Disable Risk control")  # type: ignore[attr-defined]
