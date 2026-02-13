from typing import Any, Optional, Tuple

from django import forms
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Model, QuerySet
from django.forms import ModelForm
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from rozert_pay.common.helpers.cache import memory_cache_invalidate
from rozert_pay.limits.models.const import LimitPeriod
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import (
    LimitType,
    MerchantLimit,
    MerchantLimitScope,
)
from rozert_pay.limits.services.limits import invalidate_limits_cache
from rozert_pay.payment.models import Customer, Merchant, Wallet


class CustomerLimitForm(ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        period = cleaned_data.get("period")
        customer = cleaned_data.get("customer")

        if customer and period:
            duplicate_query = CustomerLimit.objects.filter(
                customer=customer, period=period
            )
            if self.instance.pk:
                duplicate_query = duplicate_query.exclude(pk=self.instance.pk)
            if duplicate_query.exists():
                raise ValidationError(
                    _("Limit for this customer with this period already exists.")
                )
        return cleaned_data


class MerchantLimitForm(ModelForm):
    wallets = forms.ModelMultipleChoiceField(
        queryset=Wallet.objects.all(),
        required=False,
        label=_("Wallets"),
        help_text=_("Select multiple wallets for Wallet scope limits."),
    )

    class Meta:
        model = MerchantLimit
        fields = "__all__"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.scope == MerchantLimitScope.WALLET:
            self.fields["wallets"].initial = (
                Wallet.objects.filter(merchant_limits=self.instance)
                if self.instance.pk
                else []
            )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        scope = cleaned_data.get("scope")
        limit_type = cleaned_data.get("limit_type")
        period = cleaned_data.get("period")
        merchant = cleaned_data.get("merchant")
        wallet = cleaned_data.get("wallet")

        if scope == MerchantLimitScope.MERCHANT and not merchant:
            raise ValidationError(_("Merchant is required for merchant scope."))
        if (
            scope == MerchantLimitScope.WALLET
            and not wallet
            and not cleaned_data.get("wallets")
        ):
            raise ValidationError(
                _("At least one wallet is required for wallet scope.")
            )

        duplicate_query = MerchantLimit.objects.filter(
            scope=scope, limit_type=limit_type, period=period
        )
        if scope == MerchantLimitScope.MERCHANT:
            duplicate_query = duplicate_query.filter(merchant=merchant)
        elif scope == MerchantLimitScope.WALLET:
            duplicate_query = duplicate_query.filter(wallet=wallet)

        if self.instance.pk:
            duplicate_query = duplicate_query.exclude(pk=self.instance.pk)
        if duplicate_query.exists():
            raise ValidationError(
                _("Limit with this type, period, and scope/target already exists.")
            )

        return cleaned_data

    def save(self, commit: bool = True) -> MerchantLimit:
        instance = super().save(commit=False)
        if commit:
            instance.save()
            if instance.scope == MerchantLimitScope.WALLET:
                wallets = self.cleaned_data.get("wallets")
                if wallets:
                    for wallet in wallets:
                        MerchantLimit.objects.get_or_create(
                            scope=instance.scope,
                            limit_type=instance.limit_type,
                            period=instance.period,
                            wallet=wallet,
                            defaults={
                                "active": instance.active,
                                "description": instance.description,
                                "max_operations": instance.max_operations,
                                "max_decline_percent": instance.max_decline_percent,
                                "min_amount": instance.min_amount,
                                "max_amount": instance.max_amount,
                                "total_amount": instance.total_amount,
                                "max_ratio": instance.max_ratio,
                                "burst_minutes": instance.burst_minutes,
                                "decline_on_exceed": instance.decline_on_exceed,
                                "is_critical": instance.is_critical,
                            },
                        )
        return instance


class BaseLimitAdmin(admin.ModelAdmin):
    list_display = (
        "status_colored",
        "description",
        "period_display",
        "decline_on_exceed",
        "is_critical",
        "audit_link",
    )
    list_filter = ("active", "period", "decline_on_exceed", "is_critical")
    search_fields = ("description",)
    actions = ["invalidate_cache_action"]

    def status_colored(self, obj: Model) -> str:
        color = "green" if obj.active else "red"
        return format_html(
            "<span style='color: {};'>{}</span>",
            color,
            _("Active") if obj.active else _("Inactive"),
        )

    status_colored.short_description = _("Status")

    def period_display(self, obj: Model) -> str:
        return dict(LimitPeriod.choices).get(obj.period, obj.period)

    period_display.short_description = _("Period")

    def audit_link(self, obj: Model) -> str:
        content_type = ContentType.objects.get_for_model(obj.__class__)
        audit_url = (
            reverse("admin:admin_logentry_changelist")
            + f"?content_type__id__exact={content_type.id}&object_id__exact={obj.pk}"
        )
        return format_html("<a href='{}'>{}</a>", audit_url, _("View Audit"))

    audit_link.short_description = _("Audit")

    def invalidate_cache_action(self, request: HttpRequest, queryset: QuerySet) -> None:
        invalidate_limits_cache()
        self.message_user(request, _("Cache invalidated successfully."))

    invalidate_cache_action.short_description = _("Invalidate limits cache")

    def get_fieldsets(
        self, request: HttpRequest, obj: Optional[Model] = None
    ) -> list[Tuple[Optional[str], dict[str, Any]]]:
        fieldsets = [
            (
                _("General"),
                {
                    "fields": (
                        "active",
                        "description",
                        "period",
                        "decline_on_exceed",
                        "is_critical",
                    ),
                },
            ),
        ]
        return fieldsets

    def delete_model(self, request: HttpRequest, obj: Model) -> None:
        self._check_deletion(request, obj)
        super().delete_model(request, obj)
        invalidate_limits_cache()

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet) -> None:
        for obj in queryset:
            self._check_deletion(request, obj)
        super().delete_queryset(request, queryset)
        memory_cache_invalidate("active_limits")

    def _check_deletion(self, request: HttpRequest, obj: Model) -> None:
        related_objects = []
        for rel in obj._meta.related_objects:
            related_count = rel.related_model.objects.filter(
                **{rel.field.name: obj}
            ).count()
            if related_count > 0:
                related_objects.append(
                    f"{rel.related_model._meta.verbose_name_plural}: {related_count}"
                )

        if related_objects:
            self.message_user(
                request,
                _(
                    f"Warning: This limit is tied to {', '.join(related_objects)}. "
                    f"Deleting it will unbind these relations."
                ),
                level="warning",
            )

    def save_model(
        self, request: HttpRequest, obj: Model, form: ModelForm, change: bool
    ) -> None:
        super().save_model(request, obj, form, change)
        memory_cache_invalidate("active_limits")


@admin.register(CustomerLimit)
class CustomerLimitAdmin(BaseLimitAdmin):
    form = CustomerLimitForm
    list_display = (
        "status_colored",
        "customer",
        "description",
        "period_display",
        "max_successful_operations",
        "max_failed_operations",
        "min_operation_amount",
        "max_operation_amount",
        "total_successful_amount",
        "decline_on_exceed",
        "is_critical",
        "audit_link",
    )
    list_filter = BaseLimitAdmin.list_filter + ("customer",)
    search_fields = BaseLimitAdmin.search_fields + ("customer__email",)
    raw_id_fields = ("customer",)

    def get_fieldsets(
        self, request: HttpRequest, obj: Optional[Model] = None
    ) -> list[Tuple[Optional[str], dict[str, Any]]]:
        fieldsets = super().get_fieldsets(request, obj)
        fieldsets.append(
            (
                _("Limit Settings"),
                {
                    "fields": (
                        "customer",
                        "max_successful_operations",
                        "max_failed_operations",
                        "min_operation_amount",
                        "max_operation_amount",
                        "total_successful_amount",
                    ),
                },
            ),
        )
        return fieldsets

    def get_form(
        self, request: HttpRequest, obj: Optional[Model] = None, **kwargs
    ) -> type:
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["customer"].queryset = Customer.objects.all()
        return form


@admin.register(MerchantLimit)
class MerchantLimitAdmin(BaseLimitAdmin):
    form = MerchantLimitForm
    list_display = (
        "status_colored",
        "scope_name",
        "merchant_name",
        "wallet_display",
        "limit_type_display",
        "description",
        "period_display",
        "max_operations",
        "max_decline_percent",
        "min_amount",
        "max_amount",
        "total_amount",
        "max_ratio",
        "burst_minutes",
        "decline_on_exceed",
        "is_critical",
        "audit_link",
    )
    list_filter = BaseLimitAdmin.list_filter + (
        "scope",
        "limit_type",
        "merchant",
        "wallet",
    )
    search_fields = BaseLimitAdmin.search_fields + (
        "merchant__name",
        "wallet__name",
    )
    raw_id_fields = ("merchant", "wallet")

    def scope_name(self, obj: MerchantLimit) -> str:
        return dict(MerchantLimitScope.choices).get(obj.scope, obj.scope)

    scope_name.short_description = _("Scope")

    def merchant_name(self, obj: MerchantLimit) -> str:
        return obj.merchant.name if obj.merchant else "-"

    merchant_name.short_description = _("Merchant")

    def wallet_display(self, obj: MerchantLimit) -> str:
        return obj.wallet.name if obj.wallet else "-"

    wallet_display.short_description = _("Wallet")

    def limit_type_display(self, obj: MerchantLimit) -> str:
        return dict(LimitType.choices).get(obj.limit_type, obj.limit_type)

    limit_type_display.short_description = _("Limit Type")

    def get_fieldsets(
        self, request: HttpRequest, obj: Optional[Model] = None
    ) -> list[Tuple[Optional[str], dict[str, Any]]]:
        fieldsets = super().get_fieldsets(request, obj)
        fieldsets.append(
            (
                _("Limit Settings"),
                {
                    "fields": (
                        "scope",
                        "merchant",
                        "wallet",
                        "wallets",
                        "limit_type",
                        "max_operations",
                        "max_decline_percent",
                        "min_amount",
                        "max_amount",
                        "total_amount",
                        "max_ratio",
                        "burst_minutes",
                    ),
                },
            ),
        )
        return fieldsets

    def get_form(
        self, request: HttpRequest, obj: Optional[Model] = None, **kwargs
    ) -> type:
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["merchant"].queryset = Merchant.objects.all()
        form.base_fields["wallet"].queryset = Wallet.objects.all()
        return form

    def get_list_display(self, request: HttpRequest) -> tuple[str, ...]:
        list_display = super().get_list_display(request)
        if not request.user.is_superuser:
            list_display = tuple(x for x in list_display if x not in ["is_critical"])
        return list_display
