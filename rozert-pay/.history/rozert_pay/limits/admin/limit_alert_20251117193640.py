from typing import Optional

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.limits.const import CRITICAL_LIMIT_COLOR, REGULAR_LIMIT_COLOR
from rozert_pay.limits.models.common import LimitCategory
from rozert_pay.limits.models.limit_alert import LimitAlert


@admin.register(LimitAlert)
class LimitAlertAdmin(admin.ModelAdmin):
    change_form_template = "limits/change_form.html"
    list_display = (
        "limit_type_colored",
        "is_active",
        "is_notified",
        "transaction_display",
        "customer_limit_display",
        "merchant_limit_display",
        "created_at",
        "notification_text_display",
        "extra_data",
        "links",
        "acknowledged_by_display",
    )
    list_filter = (
        "is_active",
        "is_notified",
        "customer_limit",
        "merchant_limit",
        "created_at",
        "is_notified",
    )
    search_fields = (
        "transaction__uuid",
        "customer_limit__description",
        "merchant_limit__description",
        "notification_text",
    )
    raw_id_fields = ("customer_limit", "merchant_limit", "transaction")
    readonly_fields = (
        "links",
        "notification_text_display",
        "is_notified",
        "acknowledged_by_display",
    )

    @admin.display(description=_("Limit Type"))
    def limit_type_colored(self, obj: LimitAlert) -> str:
        limit_type = "Customer" if obj.customer_limit else "Merchant"
        limit_category = " Risk" if obj.customer_limit and obj.customer_limit.category == LimitCategory.RISK else " Business" if obj.customer_limit and obj.customer_limit.category == LimitCategory.BUSINESS else ""
        color = CRITICAL_LIMIT_COLOR if obj.is_critical else REGULAR_LIMIT_COLOR
        return format_html("<span style='color: {};'>{}</span>", color, limit_type)

    @admin.display(description=_("Transaction"))
    def transaction_display(self, obj: LimitAlert) -> str:
        return (
            f"{obj.transaction.type} #{obj.transaction.id}"
            f" ({obj.transaction.amount} {obj.transaction.currency})"
        )

    @admin.display(description=_("Customer Limit"))
    def customer_limit_display(self, obj: LimitAlert) -> str:
        return obj.customer_limit.description if obj.customer_limit else "-"

    @admin.display(description=_("Merchant Limit"))
    def merchant_limit_display(self, obj: LimitAlert) -> str:
        return obj.merchant_limit.description if obj.merchant_limit else "-"

    @admin.display(description=_("Notification Text"))
    def notification_text_display(self, obj: LimitAlert) -> str:
        return obj.notification_text if obj.notification_text else "-"

    @admin.display(description=_("Acknowledged By"))
    def acknowledged_by_display(self, obj: LimitAlert) -> str:
        users = obj.acknowledged_by.all()
        if not users.exists():
            return "-"

        links = []
        for user in users:
            user_url = reverse("admin:account_user_change", args=[user.pk])
            links.append(f'<a href="{user_url}">{user.pk}</a>')

        return format_html(", ".join(links))

    @admin.display(description=_("Extra Data"))
    def extra_data(self, obj: LimitAlert) -> str:
        return str(obj.extra)

    @admin.display(description=_("Links"))
    def links(self, obj: LimitAlert) -> str:
        data: list[LinkItem] = []
        if obj.transaction:
            data.append(
                {
                    "link": reverse(
                        "admin:payment_paymenttransaction_change",
                        args=[obj.transaction.pk],
                    ),
                    "name": _("Transaction"),
                }
            )
        if obj.customer_limit:
            if obj.customer_limit.category == LimitCategory.RISK:
                link = reverse(
                    "admin:limits_riskcustomerlimit_change",
                    args=[obj.customer_limit.pk],
                )
            else:
                link = reverse(
                    "admin:limits_businesscustomerlimit_change",
                    args=[obj.customer_limit.pk],
                )
            data.append({"link": link, "name": _("Customer Limit")})
        if obj.merchant_limit:
            data.append(
                {
                    "link": reverse(
                        "admin:limits_merchantlimit_change",
                        args=[obj.merchant_limit.pk],
                    ),
                    "name": _("Merchant Limit"),
                }
            )

        content_type = ContentType.objects.get_for_model(obj.__class__)
        params = {"content_type__id__exact": str(content_type.id)}
        if isinstance(obj.pk, int):
            params["object_id__exact"] = str(obj.pk)
        else:
            params["object_pk__exact"] = str(obj.pk)

        audit_url = (
            reverse("admin:auditlog_logentry_changelist") + "?" + urlencode(params)
        )
        data.append({"link": audit_url, "name": _("Audit")})

        return make_links(data)

    def get_fieldsets(self, request: HttpRequest, obj: Optional[Model] = None) -> list:
        fieldsets = [
            (
                str(_("General")),
                {
                    "fields": [
                        "is_active",
                        "is_notified",
                        "transaction",
                        "customer_limit",
                        "merchant_limit",
                        "notification_text",
                        "extra",
                        "acknowledged_by_display",
                    ],
                },
            ),
        ]
        return fieldsets
