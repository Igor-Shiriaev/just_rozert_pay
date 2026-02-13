import typing

import pydantic
from bm.django_utils.widgets import JSONEditorWidget
from django import forms
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.http import HttpRequest
from django.template import engines
from django.utils.safestring import mark_safe
from rozert_pay.payment import entities, models
from rozert_pay.payment.admin import BaseRozertAdmin
from rozert_pay.payment.admin.mixins import RiskControlActionsMixin
from rozert_pay.payment.permissions import CommonUserPermissions


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

        fields_info = []
        for name, field in entities.CardData.model_fields.items():
            fields_info.append(
                {
                    "name": name,
                    "required": field.is_required(),
                }
            )

        help_text = (
            engines.all()[0]
            .from_string(
                """
Card data format:
<ul>
{% for f in fields_info %}
<li><b>{{f.name}}</b>: {%if f.required%} REQUIRED{%endif%}</li>
{% endfor %}
</ul>
            """
            )
            .render(
                context={
                    "fields_info": fields_info,
                }
            )
        )
        self.fields["card_data"].help_text = help_text

    def clean(self):
        cleaned_data = super().clean()
        card_data = cleaned_data.get("card_data")
        if card_data is not None:
            try:
                entities.CardData(**card_data)
            except pydantic.ValidationError as e:
                error_messages = []
                for error in e.errors():
                    field = error.get("loc", ("unknown",))[-1]
                    message = error.get("msg", "Invalid value")
                    error_messages.append(f"{field}: {message}")
                raise ValidationError(
                    {"card_data": "Invalid card data: " + "; ".join(error_messages)}
                )
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
            readonly_fields = (
                *readonly_fields,
                "email_encrypted",
                "phone_encrypted",
                "extra_encrypted",
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
    pass
