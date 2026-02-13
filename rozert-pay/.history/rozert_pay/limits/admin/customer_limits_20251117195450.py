from typing import Any, Optional
from django.db.models import Model, QuerySet

from auditlog.mixins import LogEntryAdminMixin
from django.contrib import admin
from django.db.models import Model
from django.forms import ModelForm
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from rozert_pay.limits.models.customer_limits import (
    BusinessCustomerLimit,
    CustomerLimit,
    RiskCustomerLimit,
)
from rozert_pay.limits.models.merchant_limits import MerchantLimit
from rozert_pay.payment.models import Customer

from .base import BaseLimitAdmin
from .forms import CustomerLimitForm


# @admin.register(CustomerLimit)
class CustomerLimitAdmin(LogEntryAdminMixin, BaseLimitAdmin):
    form = CustomerLimitForm
    change_form_template = "limits/change_form.html"
    list_display = (  # type: ignore[assignment]
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
        "links",
    )
    list_filter = ("active", "period", "decline_on_exceed", "is_critical", "customer")  # type: ignore[assignment]
    search_fields = ("description", "customer__email")  # type: ignore[assignment]
    raw_id_fields = ("customer",)
    list_select_related = ("customer",)
    filter_horizontal = ("notification_groups",)

    def get_fieldsets(
        self, request: HttpRequest, obj: Optional[Model] = None
    ) -> list[Any]:
        fieldsets: list[Any] = super().get_fieldsets(request, obj)
        fieldsets.append(
            (
                str(_("Limit Settings")),
                {
                    "fields": [
                        "period",
                        "customer",
                        "max_successful_operations",
                        "max_failed_operations",
                        "min_operation_amount",
                        "max_operation_amount",
                        "total_successful_amount",
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
        form: type[ModelForm] = super().get_form(request, obj, change, **kwargs)
        if "customer" in form.base_fields:
            form.base_fields["customer"].queryset = Customer.objects.all()  # type: ignore[attr-defined]
        return form


@admin.register(RiskCustomerLimit)
class RiskCustomerLimitAdmin(CustomerLimitAdmin):
    actions = ["enable_risk_control_action", "disable_risk_control_action"]

    @admin.display(description=_("Enable Risk control"))
    def enable_risk_control_action(
        self,
        request: HttpRequest,
        queryset: QuerySet[CustomerLimit],
    ) -> None:
        queryset.update(active=True)
        self.message_user(request, _("Risk control enabled successfully."))

    @admin.display(description=_("Disable Risk control"))
    def disable_risk_control_action(
        self,
        request: HttpRequest,
        queryset: QuerySet[CustomerLimit],
    ) -> None:
        queryset.update(active=False)
        self.message_user(request, _("Risk control disabled successfully."))


@admin.register(BusinessCustomerLimit)
class BusinessCustomerLimitAdmin(CustomerLimitAdmin):
    pass
