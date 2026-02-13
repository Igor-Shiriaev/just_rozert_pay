from django.contrib import messages
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django.db import models
from django_object_actions import action
from rozert_pay.payment.models import Merchant, Wallet, Customer


class RiskControlActionsMixin:
    @action(label=_("Enable Risk control"), description=_("Enable Risk control"))
    def enable_risk_control(self, request: HttpRequest, obj: models.Model) -> None:
        if not isinstance(obj, (Merchant, Wallet, Customer)):
            raise ValueError("Object must be a Merchant, Wallet or Customer")
        obj.risk_control = True
        obj.save()
        messages.success(request, "Risk control enabled successfully.")

    @action(label=_("Disable Risk control"), description=_("Disable Risk control"))
    def disable_risk_control(self, request: HttpRequest, obj: models.Model) -> None:
        if not isinstance(obj, (Merchant, Wallet, Customer)):
            raise ValueError("Object must be a Merchant, Wallet or Customer")
        obj.risk_control = False
        obj.save()
        messages.success(request, "Risk control disabled successfully.")
