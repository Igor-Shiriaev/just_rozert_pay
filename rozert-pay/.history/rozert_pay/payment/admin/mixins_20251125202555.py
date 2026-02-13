from typing import Any


class DynamicFieldsetMixin:
    sections: tuple[dict[str, Any], ...] = ()

    def get_fieldsets(self, request, obj=None) -> list[tuple[str | None, dict]]:  # type: ignore[override]
        fieldsets: list[tuple[str | None, dict]] = super().get_fieldsets(request, obj)  # type: ignore[assignment, misc]

        new_fieldsets: list[tuple[str | None, dict]] = []

        for name, fieldset_cfg in fieldsets:
            fields: tuple[str, ...] = fieldset_cfg["fields"]
            new_fields = list(fields)
            new_fieldset_cfg = {
                **fieldset_cfg,
                "fields": new_fields,
            }

            for scfg in self.sections:
                section_fields: tuple[str, ...] = scfg["fields"]
                for field in section_fields:
                    if field in new_fields:
                        new_fields.remove(field)

            new_fieldsets.append((name, new_fieldset_cfg))

        for scfg in self.sections:
            section_fields = scfg["fields"]
            section_name = scfg["name"]
            section_config = {"fields": section_fields}

            if "description" in scfg:
                section_config["description"] = scfg["description"]
            if "classes" in scfg:
                section_config["classes"] = scfg["classes"]

            new_fieldsets.append((section_name, section_config))

        return new_fieldsets
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
