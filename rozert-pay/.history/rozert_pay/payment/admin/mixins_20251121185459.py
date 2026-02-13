from typing import Iterable

from django.contrib import messages
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django.db import models
from django_object_actions import action
from rozert_pay.payment import 


class RiskControlActionsMixin:
    @action(label=_("Enable Risk control"), description=_("Enable Risk control"))
    def enable_risk_control(self, request: HttpRequest, obj: models.Model) -> None:
        if not isinstance(obj, (models.Merchant, models.Wallet, models.Customer)):
            raise ValueError("Object must be a Merchant, Wallet or Customer")
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
