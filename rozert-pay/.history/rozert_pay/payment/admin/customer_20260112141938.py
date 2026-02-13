import typing

import pydantic
from bm.django_utils.widgets import JSONEditorWidget
from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.http import HttpRequest
from django.utils.safestring import mark_safe
from rozert_pay.payment import entities, models
from rozert_pay.payment.admin import BaseRozertAdmin
from rozert_pay.payment.admin.mixins import RiskControlActionsMixin


class CustomerCardForm(forms.ModelForm):
    class Meta:
        model = models.CustomerCard
        fields = "__all__"
        exclude = ["_card_data", "card_data_encrypted"]

    card_data = forms.JSONField(
        widget=JSONEditorWidget(mode=JSONEditorWidget.MODE_CODE),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.card_data:
            self.fields["card_data"].initial = self.instance.card_data
        else:
            self.fields["card_data"].initial = {}

    def clean(self):
        cleaned_data = super().clean()
        card_data = cleaned_data.get("card_data")
        if card_data is not None:
            self.instance.card_data = card_data
        return cleaned_data


@admin.register(models.CustomerCard)
class CustomerCardAdmin(BaseRozertAdmin):
    form = CustomerCardForm

    if settings.IS_PRODUCTION:
        exclude = ["_card_data", "card_data_encrypted"]
        readonly_fields = ["card_info"]

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
        "email",
        "uuid",
    ]

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: models.Customer | None = None,
    ) -> tuple[str, ...]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is None and "risk_control" in readonly_fields:
            readonly_fields.remove("risk_control")
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
    pass
