import json
import typing

from django.conf import settings
from django.contrib import admin
from django.forms import ModelForm
from django.http import HttpRequest
from django.utils.safestring import mark_safe
from rozert_pay.payment import models
from rozert_pay.payment.admin import BaseRozertAdmin
from rozert_pay.payment.admin.mixins import RiskControlActionsMixin
from rozert_pay.payment.permissions import CommonUserPermissions


@admin.register(models.CustomerCard)
class CustomerCardAdmin(BaseRozertAdmin):
    if settings.IS_PRODUCTION:
        exclude = ["card_data"]
        readonly_fields = ["card_info"]

    def save_form(self, request, form, change):
        i: models.CustomerCard = form.instance
        i.card_data = json.loads(form.cleaned_data["card_data"])
        return super().save_form(request, form, change)

    def card_info(self, obj: models.CustomerCard) -> str:
        ce = obj.card_data_entity
        if not ce:
            return "-"

        masked_card = f"{ce.card_num.get_secret_value()[:8]}***{ce.card_num.get_secret_value()[-4:]}"
        return mark_safe(
            f"""
<ul>
    <li>Card num: {masked_card}</li>
    <li>Card holder: {ce.card_holder}</li>
    <li>Card expires: {ce.card_expiration}</li>
</ul>
        """
        )


@admin.register(models.Customer)
class CustomerAdmin(BaseRozertAdmin, RiskControlActionsMixin):
    change_actions: list[str] = list(RiskControlActionsMixin.change_actions)

    readonly_fields: tuple[str, ...] = ("risk_control",)

    search_fields = [
        "uuid",
    ]

    exclude = [
        "_email",
        "_phone",
        "_extra",
        "email_deterministic_hash",
        "phone_hash",
    ]

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: models.Customer | None = None,
    ) -> tuple[str, ...]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is None and "risk_control" in readonly_fields:
            readonly_fields.remove("risk_control")

        if not CommonUserPermissions.CAN_VIEW_PERSONAL_DATA.allowed_for(request.user):
            readonly_fields.extend(
                (
                    "email_encrypted",
                    "phone_encrypted",
                    "extra_encrypted",
                )
            )

        return tuple(readonly_fields)

    def get_form(
        self,
        request: HttpRequest,
        obj: models.Customer | None = None,
        change: bool = False,
        **kwargs: typing.Any,
    ) -> type[ModelForm]:
        form = super().get_form(request, obj, change, **kwargs)
        if obj is None and "risk_control" in form.base_fields:
            form.base_fields["risk_control"].initial = True
        return form


@admin.register(models.CustomerExternalPaymentSystemAccount)
class CustomerExternalPaymentSystemAccountAdmin(BaseRozertAdmin):
    list_display = [
        "id",
        "uuid",
        "customer",
        "unique_account_number",
        "system_type",
        "active",
    ]
    list_filter = [
        "system_type",
    ]

    list_select_related = ["customer"]
    raw_id_fields = ["customer", "wallet"]
