from django.contrib import messages
from django.db import models
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django_object_actions import action  # type: ignore[attr-defined]
from rozert_pay.payment.models import Customer, Merchant, Wallet


class RiskControlActionsMixin:
    change_actions: list[str] = ["enable_risk_control", "disable_risk_control"]

    @action(label=_("Enable Risk control"), description=_("Enable Risk control"))  # type: ignore[misc]
    def enable_risk_control(self, request: HttpRequest, obj: models.Model) -> None:
        if not isinstance(obj, (Merchant, Wallet, Customer)):
            raise ValueError("Object must be a Merchant, Wallet or Customer")
        obj.risk_control = True
        obj.save()
        messages.success(request, "Risk control enabled successfully.")

    @action(label=_("Disable Risk control"), description=_("Disable Risk control"))  # type: ignore[misc]
    def disable_risk_control(self, request: HttpRequest, obj: models.Model) -> None:
        if not isinstance(obj, (Merchant, Wallet, Customer)):
            raise ValueError("Object must be a Merchant, Wallet or Customer")
        obj.risk_control = False
        obj.save()
        messages.success(request, "Risk control disabled successfully.")
