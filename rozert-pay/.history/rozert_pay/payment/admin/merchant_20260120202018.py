import random

from bm.django_utils.widgets import JSONEditorWidget
from django import forms
from django.contrib import admin
from django.contrib.admin import ModelAdmin as BaseModelAdmin
from django.core.exceptions import ValidationError
from django.db.models import JSONField
from django.http import HttpRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_object_actions import DjangoObjectActions
from rozert_pay.account.models import User
from rozert_pay.common.encryption import EncryptedField
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.common.templatetags.custom_filters import admin_display_context
from rozert_pay.payment import models
from rozert_pay.payment.admin.mixins import RiskControlActionsMixin


class BaseRozertAdmin(DjangoObjectActions, BaseModelAdmin):
    formfield_overrides = {
        JSONField: {"widget": JSONEditorWidget(mode=JSONEditorWidget.MODE_CODE)},
        EncryptedField: {"widget": JSONEditorWidget(mode=JSONEditorWidget.MODE_CODE)},
    }

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if object_id:
            with admin_display_context(
                request.user, self.get_object(request, object_id)
            ):
                tr: TemplateResponse | HttpResponseRedirect = super().changeform_view(  # type: ignore[assignment]
                    request, object_id, form_url, extra_context
                )
                if isinstance(tr, TemplateResponse):
                    return tr.render()
                return tr

        return super().changeform_view(request, object_id, form_url, extra_context)


def generate_password(length: int = 12) -> str:
    symbols = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(random.choices(symbols, k=length))


class MerchantGroupForm(forms.ModelForm):
    user_email = forms.EmailField(required=True)
    user_password = forms.CharField(
        min_length=8,
        max_length=100,
        required=True,
    )

    def clean_user_email(self) -> str:
        email = self.cleaned_data["user_email"]
        if (
            email
            and not self.instance.user_id
            and User.objects.filter(email=email).exists()
        ):
            raise ValidationError("User with this email already exists")
        return email

    def save(self, commit: bool = True) -> models.MerchantGroup:
        if not self.instance.user_id:
            user = User.objects.create_user(
                email=self.cleaned_data["user_email"],
                password=self.cleaned_data["user_password"],
            )

            self.instance.user = user
        return super().save(commit=commit)

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)

        if self.instance.user_id:
            self.fields["user_email"] = forms.CharField(
                required=False, initial=self.instance.user.email, disabled=True
            )
            self.fields["user_password"] = forms.CharField(
                widget=forms.HiddenInput(), required=False
            )
        else:
            self.fields["user_password"].initial = generate_password()

    class Meta:
        model = models.MerchantGroup
        fields = "__all__"
        exclude = ("user",)


class MerchantForm(forms.ModelForm):
    class Meta:
        model = models.Merchant
        fields = "__all__"

    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)

        self.fields["secret_key"].initial = generate_password(32)


@admin.register(models.MerchantGroup)
class MerchantGroupAdmin(BaseRozertAdmin):
    form = MerchantGroupForm
    list_display = ("id", "name", "created_at", "updated_at")
    search_fields = ("name", "description")
    list_filter = ("created_at", "updated_at")


@admin.register(models.Merchant)
class MerchantAdmin(BaseRozertAdmin, RiskControlActionsMixin):
    change_actions: list[str] = list(RiskControlActionsMixin.change_actions)

    form = MerchantForm
    list_display = ("id", "name", "merchant_group", "created_at", "updated_at")
    search_fields = ("name", "merchant_group__name", "id", "merchant_group__id")
    list_select_related = ("merchant_group",)
    date_hierarchy = "created_at"
    autocomplete_fields = ("merchant_group",)
    readonly_fields: tuple[str, ...] = ("risk_control",)

    def links(self, obj: models.Merchant) -> str:
        data: list[LinkItem] = [
            {
                "link": reverse("admin:limits_merchantlimit_changelist")
                + f"?merchant__id__exact={obj.pk}",
                "name": _("Merchant Limits"),
            },
            {
                "link": reverse("admin:payment_wallet_changelist")
                + f"?merchant__id__exact={obj.pk}",
                "name": _("Wallets"),
            },
        ]
        return make_links(data)

    links.short_description = str(_("Links"))  # type: ignore[attr-defined]

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: models.Merchant | None = None,
    ) -> tuple[str, ...]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is None and "risk_control" in readonly_fields:
            readonly_fields.remove("risk_control")
        return tuple(readonly_fields)
