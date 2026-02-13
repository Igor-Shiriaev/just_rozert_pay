from typing import Any, Callable, Optional

from auditlog.mixins import LogEntryAdminMixin
from django.contrib import admin
from django.db.models import Model
from django.forms import ModelForm
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from rozert_pay.limits.admin.base import BaseLimitAdmin, CategoryLimitAdminBase
from rozert_pay.limits.admin.forms import MerchantLimitForm
from rozert_pay.limits.models.common import LimitCategory
from rozert_pay.limits.models.merchant_limits import (
    BusinessMerchantLimit,
    GlobalRiskMerchantLimit,
    LimitType,
    MerchantLimit,
    MerchantLimitScope,
    RiskMerchantLimit,
)
from rozert_pay.payment.models import Merchant, Wallet


@admin.register(MerchantLimit)
class MerchantLimitAdmin(LogEntryAdminMixin, BaseLimitAdmin):
    changelist_actions = (*BaseLimitAdmin.changelist_actions,)

    form = MerchantLimitForm
    change_form_template = "limits/change_form.html"
    list_display = (  # type: ignore[assignment]
        "status_colored",
        "scope_name",
        "merchant_name",
        "wallet_display",
        "limit_type_display",
        "description",
        "period_display",
        "max_operations",
        "max_overall_decline_percent_display",
        "max_withdrawal_decline_percent_display",
        "max_deposit_decline_percent_display",
        "min_amount",
        "max_amount",
        "total_amount",
        "max_ratio_display",
        "burst_minutes",
        "decline_on_exceed",
        "is_critical",
        "links",
    )
    list_filter = (  # type: ignore[assignment]
        "active",
        "period",
        "decline_on_exceed",
        "is_critical",
        "scope",
        "limit_type",
        "merchant",
        "wallet",
    )
    search_fields = ("description", "merchant__name", "wallet__name")  # type: ignore[assignment]
    raw_id_fields = ("merchant", "wallet")
    list_select_related = ("merchant", "wallet")
    filter_horizontal = ("notification_groups",)

    def has_module_permission(self, request: HttpRequest) -> bool:
        return False

    @admin.display(description=_("Scope"))
    def scope_name(self, obj: MerchantLimit) -> str:
        return dict(MerchantLimitScope.choices).get(obj.scope, obj.scope)

    @admin.display(description=_("Merchant"))
    def merchant_name(self, obj: MerchantLimit) -> str:
        return obj.merchant.name if obj.merchant else "-"

    @admin.display(description=_("Wallet"))
    def wallet_display(self, obj: MerchantLimit) -> str:
        return obj.wallet.name if obj.wallet else "-"

    @admin.display(description=_("Limit Type"))
    def limit_type_display(self, obj: MerchantLimit) -> str:
        return dict(LimitType.choices).get(obj.limit_type, obj.limit_type)

    @admin.display(description=_("Max Overall Decline %"))
    def max_overall_decline_percent_display(self, obj: MerchantLimit) -> str:
        if obj.max_overall_decline_percent is not None:
            return f"{obj.max_overall_decline_percent}%"
        return "-"

    @admin.display(description=_("Max Withdrawal Decline %"))
    def max_withdrawal_decline_percent_display(self, obj: MerchantLimit) -> str:
        if obj.max_withdrawal_decline_percent is not None:
            return f"{obj.max_withdrawal_decline_percent}%"
        return "-"

    @admin.display(description=_("Max Deposit Decline %"))
    def max_deposit_decline_percent_display(self, obj: MerchantLimit) -> str:
        if obj.max_deposit_decline_percent is not None:
            return f"{obj.max_deposit_decline_percent}%"
        return "-"

    @admin.display(description=_("Max Ratio %"))
    def max_ratio_display(self, obj: MerchantLimit) -> str:
        if obj.max_ratio is not None:
            return f"{obj.max_ratio}%"
        return "-"

    def get_fieldsets(
        self,
        request: HttpRequest,
        obj: Optional[Model] = None,
    ) -> list[Any]:
        fieldsets: list[Any] = super().get_fieldsets(request, obj)
        fieldsets.append(
            (
                str(_("Limit Settings")),
                {
                    "fields": [
                        "scope",
                        "merchant",
                        "wallet",
                        "limit_type",
                        "period",
                        "max_operations",
                        "max_overall_decline_percent",
                        "max_withdrawal_decline_percent",
                        "max_deposit_decline_percent",
                        "min_amount",
                        "max_amount",
                        "total_amount",
                        "max_ratio",
                        "burst_minutes",
                    ],
                },
            ),
        )
        return fieldsets

    def get_form(
        self,
        request: HttpRequest,
        obj: Any | None = None,
        change: bool = False,
        **kwargs: Any,
    ) -> type[ModelForm]:
        form: type[ModelForm] = super().get_form(request, obj, **kwargs)
        if "merchant" in form.base_fields:
            form.base_fields["merchant"].queryset = Merchant.objects.all()  # type: ignore[attr-defined]
        if "wallet" in form.base_fields:
            form.base_fields["wallet"].queryset = Wallet.objects.all()  # type: ignore[attr-defined]
        return form

    def get_list_display(
        self, request: HttpRequest
    ) -> (
        list[str | Callable[[Any], str | bool]]
        | tuple[str | Callable[[Any], str | bool], ...]
    ):
        list_display = super().get_list_display(request)
        if not request.user.is_superuser:
            list_display = tuple(
                field for field in list_display if field != "is_critical"
            )
        return list_display


@admin.register(RiskMerchantLimit)
class RiskMerchantLimitAdmin(CategoryLimitAdminBase, MerchantLimitAdmin):
    category = LimitCategory.RISK
    limit_model_class = MerchantLimit
    readonly_fields: tuple[str, ...] = ("links", "category")
    changelist_actions = (*MerchantLimitAdmin.changelist_actions,)


@admin.register(BusinessMerchantLimit)
class BusinessMerchantLimitAdmin(CategoryLimitAdminBase, MerchantLimitAdmin):
    category = LimitCategory.BUSINESS
    limit_model_class = MerchantLimit
    readonly_fields: tuple[str, ...] = ("links", "category")

    def has_module_permission(self, request: HttpRequest) -> bool:
        return True

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: Optional[Model] = None,
    ) -> tuple[str, ...]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is None and "category" in readonly_fields:
            readonly_fields.remove("category")
        return tuple(readonly_fields)

    def get_form(
        self,
        request: HttpRequest,
        obj: MerchantLimit | None = None,
        change: bool = False,
        **kwargs: Any,
    ) -> type[ModelForm]:
        form = super().get_form(request, obj, change, **kwargs)
        if obj is None and "category" in form.base_fields:
            form.base_fields["category"].initial = LimitCategory.BUSINESS
            form.base_fields["category"].disabled = True
        return form

    def save_model(
        self,
        request: HttpRequest,
        obj: MerchantLimit | CustomerLimit,
        form: Any,
        change: bool,
    ) -> None:
        if not change and isinstance(obj, MerchantLimit):
            obj.category = LimitCategory.BUSINESS
        super().save_model(request, obj, form, change)


@admin.register(GlobalRiskMerchantLimit)
class GlobalRiskMerchantLimitAdmin(MerchantLimitAdmin):
    readonly_fields: tuple[str, ...] = ("links", "category")

    changelist_actions = (*MerchantLimitAdmin.changelist_actions,)

    def has_module_permission(self, request: HttpRequest) -> bool:
        return True

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: Optional[Model] = None,
    ) -> tuple[str, ...]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj is None and "category" in readonly_fields:
            readonly_fields.remove("category")
        return tuple(readonly_fields)

    def get_form(
        self,
        request: HttpRequest,
        obj: MerchantLimit | None = None,
        change: bool = False,
        **kwargs: Any,
    ) -> type[ModelForm]:
        form = super().get_form(request, obj, change, **kwargs)
        if obj is None and "category" in form.base_fields:
            form.base_fields["category"].initial = LimitCategory.GLOBAL_RISK
            form.base_fields["category"].disabled = True
        return form

    def save_model(
        self,
        request: HttpRequest,
        obj: MerchantLimit | CustomerLimit,
        form: Any,
        change: bool,
    ) -> None:
        if not change and isinstance(obj, MerchantLimit):
            obj.category = LimitCategory.GLOBAL_RISK
        super().save_model(request, obj, form, change)
