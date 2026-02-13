from typing import Any, Optional

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model, QuerySet
from django.forms import ModelForm
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.limits.const import (
    COLOR_OF_ACTIVE_STATUS,
    COLOR_OF_INACTIVE_STATUS,
    LimitPeriod,
)
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.limit_alert import LimitAlert
from rozert_pay.limits.models.merchant_limits import MerchantLimit
from rozert_pay.limits.services.limits import invalidate_limits_cache


class BaseLimitAdmin(admin.ModelAdmin):
    list_display = (
        "status_colored",
        "description",
        "period_display",
        "decline_on_exceed",
        "is_critical",
        "links",
    )
    list_filter = (
        "active",
        "period",
        "decline_on_exceed",
        "is_critical",
    )
    search_fields = ("description",)
    actions = ["invalidate_cache_action", "enable_risk_control_action", "disable_risk_control_action"]
    readonly_fields = ("links",)  # type: ignore[misc]

    @admin.display(description=_("Status"))
    def status_colored(self, obj: MerchantLimit | CustomerLimit) -> str:
        if not obj.active:
            color = COLOR_OF_INACTIVE_STATUS
            status_text = str(_("Inactive"))
        else:
            color = COLOR_OF_ACTIVE_STATUS
            status_text = str(_("Active"))
            if obj.decline_on_exceed and obj.is_critical:
                status_text = f"{status_text} ‼️"

        return format_html(
            "<span style='color: {}; white-space: nowrap;'>{}</span>",
            color,
            status_text,
        )

    @admin.display(description=_("Period"))
    def period_display(self, obj: MerchantLimit | CustomerLimit) -> str:
        return dict(LimitPeriod.choices).get(obj.period or "", obj.period or "")

    @admin.display(description=_("Links"))
    def links(self, obj: MerchantLimit | CustomerLimit) -> str:
        content_type = ContentType.objects.get_for_model(obj.__class__)
        filter_field = (
            "customer_limit" if isinstance(obj, CustomerLimit) else "merchant_limit"
        )

        params = {"content_type__id__exact": str(content_type.id)}
        if isinstance(obj.pk, int):
            params["object_id__exact"] = str(obj.pk)
        else:
            params["object_pk__exact"] = str(obj.pk)

        data: list[LinkItem] = [
            {
                "link": reverse("admin:auditlog_logentry_changelist")
                + "?"
                + urlencode(params),
                "name": _("Audit"),
            },
            {
                "link": reverse("admin:limits_limitalert_changelist")
                + f"?{filter_field}__id__exact={obj.pk}",
                "name": _("Alerts"),
            },
            {
                "link": reverse("admin:payment_paymenttransaction_changelist")
                + f"?limit_trigger_logs__{filter_field}__id__exact={obj.pk}",
                "name": _("Transactions"),
            },
        ]

        if isinstance(obj, CustomerLimit):
            data.extend(
                [
                    {
                        "link": reverse(
                            "admin:payment_customer_change", args=[obj.customer.pk]
                        ),
                        "name": _("Customer"),
                    },
                ]
            )
        elif isinstance(obj, MerchantLimit):
            if obj.merchant:
                data.append(
                    {
                        "link": reverse(
                            "admin:payment_merchant_change", args=[obj.merchant.pk]
                        ),
                        "name": _("Merchant"),
                    }
                )
            if obj.wallet:
                data.append(
                    {
                        "link": reverse(
                            "admin:payment_wallet_change", args=[obj.wallet.pk]
                        ),
                        "name": _("Wallet"),
                    }
                )

        return make_links(data)

    @admin.display(description=_("Invalidate limits cache"))
    def invalidate_cache_action(
        self, request: HttpRequest, queryset: QuerySet[MerchantLimit | CustomerLimit]
    ) -> None:
        invalidate_limits_cache()
        self.message_user(request, _("Cache invalidated successfully."))

    @admin.display(description=_("Enable Risk control"))
    def enable_risk_control_action(
        self, request: HttpRequest, queryset: QuerySet[MerchantLimit | CustomerLimit]
    ) -> None:
        switch_all_risk_limits_status()
        self.message_user(request, _("Risk control enabled successfully."))

    @admin.display(description=_("Disable Risk control"))
    def disable_risk_control_action(
        self, request: HttpRequest, queryset: QuerySet[MerchantLimit | CustomerLimit]
    ) -> None:
        invalidate_limits_cache()
        self.message_user(request, _("Risk control disabled successfully."))

    def get_fieldsets(
        self, request: HttpRequest, obj: Optional[Model] = None
    ) -> list[Any]:
        fieldsets: list[Any] = [
            (
                str(_("General")),
                {
                    "fields": [
                        "active",
                        "description",
                        "decline_on_exceed",
                        "is_critical",
                        "notification_groups",
                        "slack_channel_override",
                    ],
                },
            ),
        ]
        return fieldsets

    def delete_model(
        self, request: HttpRequest, obj: MerchantLimit | CustomerLimit
    ) -> None:
        self._check_deletion(request, obj)
        super().delete_model(request, obj)
        invalidate_limits_cache()

    def delete_queryset(
        self, request: HttpRequest, queryset: QuerySet[MerchantLimit | CustomerLimit]
    ) -> None:
        for obj in queryset:
            self._check_deletion(request, obj)
        super().delete_queryset(request, queryset)
        invalidate_limits_cache()

    def _check_deletion(
        self, request: HttpRequest, obj: MerchantLimit | CustomerLimit
    ) -> None:
        related_objects = []
        filter_kwargs = {
            (
                "customer_limit" if isinstance(obj, CustomerLimit) else "merchant_limit"
            ): obj
        }
        related_count = LimitAlert.objects.filter(**filter_kwargs).count()
        if related_count > 0:
            related_objects.append(
                f"{LimitAlert._meta.verbose_name_plural}: {related_count}"
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
        self,
        request: HttpRequest,
        obj: MerchantLimit | CustomerLimit,
        form: ModelForm,
        change: bool,
    ) -> None:
        super().save_model(request, obj, form, change)
        invalidate_limits_cache()
