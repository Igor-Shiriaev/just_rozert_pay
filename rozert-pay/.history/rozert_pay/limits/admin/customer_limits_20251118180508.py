from typing import Any, Optional
from django.db.models import Model, QuerySet

from auditlog.mixins import LogEntryAdminMixin
from django.contrib import admin
from django.db.models import Model
from django.forms import ModelForm
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from rozert_pay.limits.admin.base import BaseLimitAdmin
from rozert_pay.limits.models.customer_limits import (
    BusinessCustomerLimit,
    CustomerLimit,
    RiskCustomerLimit,
)
from rozert_pay.payment.models import Customer

from rozert_pay.feature_flags.services import update_feature_flag_status
from rozert_pay.feature_flags.const import FeatureFlagName


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
class RiskCustomerLimitAdmin(CustomerLimitAdmin, RiskControlActionsMixin):
    actions = ["enable_risk_control_action", "disable_risk_control_action"]


@admin.register(BusinessCustomerLimit)
class BusinessCustomerLimitAdmin(CustomerLimitAdmin):
    pass
