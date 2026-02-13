import json
import typing as ty
from typing import Any, Callable
from uuid import uuid4

from bm.django_utils.widgets import JSONEditorWidget
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.template import Context, Template, engines
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.payment import models
from rozert_pay.payment.admin.merchant import BaseRozertAdmin
from rozert_pay.payment.admin.mixins import RiskControlActionsMixin
from rozert_pay.payment.factories import get_payment_system_controller
from rozert_pay.payment.models import PaymentSystem
from rozert_pay.payment.services import incoming_callbacks, wallets_management


class WalletForm(forms.ModelForm):  # pragma: no cover
    instance: models.Wallet
    message_user: Callable[[str, int], None]

    class Meta:
        model = models.Wallet
        fields = "__all__"
        exclude = ["_credentials", "credentials_encrypted"]

    credentials = forms.JSONField(
        widget=JSONEditorWidget(mode=JSONEditorWidget.MODE_CODE)
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.is_sandbox = False

        merchant: models.Merchant | None = None
        if mid := self.data.get("merchant"):
            merchant = models.Merchant.objects.get(id=mid)
        elif self.instance and self.instance.merchant_id:
            merchant = self.instance.merchant

        if merchant and merchant.sandbox:
            self.fields["credentials"].required = False
            self.is_sandbox = True

        if self.instance and self.instance.credentials:
            self.fields["credentials"].initial = json.loads(self.instance.credentials)
        

        if self.instance and self.instance.system_id and (s := self.instance.system):
            controller = get_payment_system_controller(s)
            if controller:
                credentials_cls = controller.client_cls.credentials_cls
                fields_info = []
                for name, field in credentials_cls.model_fields.items():
                    fields_info.append(
                        {
                            "name": name,
                            "required": field.is_required(),
                            "type": str(field.annotation),
                        }
                    )

                help_text = (
                    engines.all()[0]
                    .from_string(
                        """
Credentials format:
<ul>
{% for f in fields_info %}
<li><b>{{f.name}}</b>: {{f.type}}{%if f.required%} REQUIRED{%endif%}</li>
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
                self.fields["credentials"].help_text = help_text

    def clean(self):
        cleaned_data = ty.cast(dict, super().clean())
        if not self.is_sandbox:
            credentials: dict | None = cleaned_data.get("credentials")
            if not credentials:
                raise ValidationError("Credentials cannot be empty")
            print('222222222222222', credentials)
            self.instance.credentials = credentials

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        assert hasattr(self, "message_user")

        old_creds = self.instance.credentials
        wallet = super().save(commit)
        new_creds = self.instance.credentials

        system: PaymentSystem = self.instance.system
        controller = get_payment_system_controller(system)
        if not controller:
            raise ValidationError(
                f"Payment system controller not found for system {system}"
            )

        wallets_management.perform_wallet_credentials_change_action(
            controller=controller,
            wallet=wallet,
            old_creds=old_creds,
            new_creds=new_creds,
            is_sandbox=self.is_sandbox,
            message_user=self.message_user,
        )

        return wallet


@admin.register(models.Wallet)
class WalletAdmin(BaseRozertAdmin, RiskControlActionsMixin):
    change_actions: list[str] = list(RiskControlActionsMixin.change_actions)

    autocomplete_fields = ["system", "merchant"]
    list_display = [
        "id",
        "merchant",
        "name",
        "created_at",
        "updated_at",
        "system",
        "sandbox",
        "links",
    ]
    search_fields = ["id", "merchant__name", "merchant__id", "system__name"]
    form = WalletForm
    ordering = ["-created_at"]
    list_select_related = ["merchant", "system"]
    readonly_fields: tuple[str, ...] = (
        "risk_control",
        "logs",
        "webhooks",
        "callback_url",
    )
    list_filter = [
        "merchant",
        "merchant__merchant_group",
    ]
    actions = ["copy"]

    def copy(self, request, queryset: QuerySet[models.Wallet]):
        for wallet in queryset:
            wallet.pk = None
            wallet.name = f"Copy of {wallet.name}"
            wallet.uuid = uuid4()
            wallet.save()
        self.message_user(request, "Done!", messages.SUCCESS)

    def webhooks(self, obj: models.Wallet) -> str:
        try:
            controller = get_payment_system_controller(obj.system)
            if not controller:
                return "ERROR: No controller found"

            client_cls = controller.client_cls
            webhooks = client_cls.get_webhooks(
                client_cls.get_credentials_from_dict(obj.credentials)
            )
            t = Template(
                """
<ul>
{% for w in webhooks %}
<li>{{ w.url }}</li>
{% endfor %}
</ul>
            """
            )
            return t.render(Context({"webhooks": webhooks}))
        except Exception as e:
            return f"ERROR: {e}"

    def sandbox(self, obj: models.Wallet) -> bool:
        return obj.merchant.sandbox

    def save_form(self, request: HttpRequest, form: WalletForm, change: bool) -> Any:
        def message_user(msg: str, level: int):
            self.message_user(request, msg, level)

        form.message_user = message_user
        return super().save_form(request, form, change)

    def callback_url(self, obj: models.Wallet) -> str:
        return incoming_callbacks.get_rozert_callback_url(
            system=obj.system,
        )

    @admin.display(description=_("Links"))
    def links(self, obj: models.Wallet) -> str:
        data: list[LinkItem] = [
            {
                "link": reverse("admin:limits_merchantlimit_changelist")
                + f"?wallet__id__exact={obj.pk}",
                "name": _("Wallet Limits"),
            },
            {
                "link": reverse("admin:payment_paymenttransaction_changelist")
                + f"?wallet__wallet__id__exact={obj.pk}",
                "name": _("Transactions"),
            },
            {
                "link": f"{settings.BETMASTER_BASE_URL}admin/payment/dbcustomcredentialrule/"
                f"?rozert_wallet_id={obj.uuid}",
                "name": _("Betmaster creds"),
            },
        ]
        return make_links(data)

    links.short_description = str(_("Links"))  # type: ignore[attr-defined]

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: models.Wallet | None = None,
    ) -> tuple[str, ...]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is None and "risk_control" in readonly_fields:
            readonly_fields.remove("risk_control")
        return tuple(readonly_fields)


@admin.register(models.CurrencyWallet)
class CurrencyWalletAdmin(BaseRozertAdmin):
    autocomplete_fields = ["wallet"]
