from typing import Iterable, Protocol

from django.contrib import messages
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django.db.models import Model
from django_object_actions import action


class HasRiskControl(Protocol):
    risk_control: bool
    
    def save(self) -> None:
        ...




class RiskControlActionsMixin:
    @action(label=_("Enable Risk control"), description=_("Enable Risk control"))
    def enable_risk_control(self, request: HttpRequest, obj: HasRiskControl) -> None:
        obj.risk_control = True
        obj.save()
        messages.success(request, "Risk control enabled successfully.")

    @action(label=_("Enable Risk control"), description=_("Enable Risk control"))
    def disable_risk_control(self, request: HttpRequest, queryset=None) -> None:
        update_feature_flag_status(
            name=FeatureFlagName.RISK_CONTROL_ENABLED,
            status=False,
        )
        messages.success(request, _("Risk control disabled successfully."))
        return None

    disable_risk_control.label = _("Disable Risk control")  # type: ignore[attr-defined]
    disable_risk_control.short_description = _("Disable Risk control")  # type: ignore[attr-defined]
