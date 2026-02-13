import json
import typing as ty
from typing import Literal, cast

from bm.django_utils.paginators import DisabledPaginator
from bm.utils import log_errors
from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from rozert_pay.account.models import User
from rozert_pay.common import const
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.limits.models.common import LimitCategory
from rozert_pay.limits.models.limit_alert import LimitAlert
from rozert_pay.payment import models
from rozert_pay.payment.admin.merchant import BaseRozertAdmin
from rozert_pay.payment.factories import get_payment_system_controller
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services.errors import Error
from rozert_pay.payment.services.transaction_actualization import (
    TransactionActualizationForm,
)


@admin.register(models.PaymentTransaction)
class PaymentTransactionAdmin(BaseRozertAdmin):
    list_display = [
        "id",
        "uuid",
        "info",
        "links",
        "decline_reason",
        "created_at",
        "updated_at",
        "id_in_payment_system",
        "decline_info",
    ]
    ordering = ["-created_at"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "links",
    ]
    search_fields = ["id_in_payment_system", "uuid"]
    change_actions = ["actualize", "set_status"]
    list_filter = [
        "wallet__wallet__system__type",
        "status",
        "currency",
    ]
    list_select_related = [
        "wallet",
        "wallet__wallet",
        "wallet__wallet__merchant",
        "wallet__wallet__system",
    ]

    @admin.action(
        description="Actualize transaction status from payment system",
        permissions=[const.Permissions.CAN_ACTUALIZE_TRANSACTION],
    )
    def actualize(self, request, trx: PaymentTransaction) -> HttpResponse | None:
        result = self.do_actualization(trx, request.POST.dict(), request.user)
        if isinstance(result, Error):
            self.message_user(request, f"Error: {result}", level="ERROR")
            return None
        elif result == "success":
            self.message_user(request, "Transaction actualized", level="SUCCESS")
            return None
        elif isinstance(result, TransactionActualizationForm):
            return render(
                request,
                "admin/actualize_transaction.html",
                context={
                    "trx": trx,
                    "form": result,
                },
            )
        else:
            raise RuntimeError

    @classmethod
    def do_actualization(
        cls,
        trx: PaymentTransaction,
        form_data: dict[str, ty.Any],
        request_user: User,
    ) -> Error | Literal["success"] | TransactionActualizationForm:
        controller = get_payment_system_controller(trx.system)
        actualizer = controller.transaction_actualizer_cls(trx, request_user)
        f = actualizer.get_form(data=form_data)
        if isinstance(f, Error):
            return f

        form = f

        match r := actualizer.save_form(form, request_user):
            case Error():
                return f
            case None:
                return "success"
            case TransactionActualizationForm():
                pass
            case _:
                raise RuntimeError(f"Unexpected case: {r}")

        return form

    @admin.action(
        description="Set transaction status",
        permissions=[const.Permissions.CAN_SET_TRANSACTION_STATUS],
    )
    @log_errors  # type: ignore[misc]
    def set_status(
        self, request: HttpRequest, trx: PaymentTransaction
    ) -> HttpResponse | None:
        controller = get_payment_system_controller(trx.system)
        setter = controller.transaction_setter_cls(trx, cast(User, request.user))
        data = request.POST.dict()
        f = setter.get_form(data=data)
        if isinstance(f, Error):
            self.message_user(request, f"Error: {f}", level="ERROR")
            return None

        form = f
        r = setter.save_form(data)
        if isinstance(r, Error):
            self.message_user(request, f"Error: {r}", level="ERROR")
            return None

        if r is None:
            self.message_user(request, "Transaction status set", level="SUCCESS")
            return None

        return render(
            request,
            "admin/actualize_transaction.html",
            context={
                "form": form,
                "trx": trx,
                "title": "Change Transaction Status",
            },
        )

    @mark_safe
    def info(self, o: models.PaymentTransaction):
        if o.status == const.TransactionStatus.FAILED:
            style = "style='color: red'"
        elif o.status == const.TransactionStatus.SUCCESS:
            style = "style='color: green'"
        else:
            style = ""
        return f"""<ul style="white-space: nowrap">
        <li>Type: {o.type}</li>
        <li>Status: <span {style}>{o.status}</span></li>
        <li>Wallet: {o.wallet.wallet}</li>
        <li>System: {o.system}</li>
        <li>Merchant: {o.wallet.wallet.merchant}</li>
        </ul>"""

    def decline_info(self, o: models.PaymentTransaction):
        if o.decline_code or o.decline_reason:
            return f'{o.decline_code or "-"}: {o.decline_reason or "-"}'
        return "-"

    def lookup_allowed(self, lookup, value, request=None):
        return True

    def links(self, obj: models.PaymentTransaction) -> str:
        data: list[LinkItem] = [
            {
                "link": reverse("admin:payment_paymenttransactioneventlog_changelist")
                + f"?transaction__id__exact={obj.id}",
                "name": _("Logs"),
            },
            {
                "link": reverse("admin:payment_incomingcallback_changelist")
                + f"?transaction__id__exact={obj.id}",
                "name": _("Incoming callbacks"),
            },
            {
                "link": reverse(
                    "admin:payment_wallet_change", args=[obj.wallet.wallet_id]
                ),
                "name": _("Wallet"),
            },
            {
                "link": (
                    f"{settings.BETMASTER_BASE_URL}admin/payment/paymenttransaction/"
                    f"?id_in_payment_system={obj.uuid}"
                ),
                "name": _("Betmaster transactions"),
            },
        ]

        if obj.customer:
            triggered_customer_limit: list[LimitAlert] = list(
                LimitAlert.objects.filter(
                    transaction_id=obj.id,
                    customer_limit__customer_id=obj.customer.pk,
                ).distinct()
            )

            if triggered_customer_limit:
                risk_customer_limits = [
                    limit
                    for limit in triggered_customer_limit
                    if limit.customer_limit.category == LimitCategory.RISK
                ]
                business_customer_limits = [
                    limit
                    for limit in triggered_customer_limit
                    if limit.customer_limit.category == LimitCategory.BUSINESS
                ]
                if risk_customer_limits:
                    data.append(
                        {
                            "link": reverse("admin:limits_riskcustomerlimit_changelist")
                            + f"?id__in={','.join(str(limit.customer_limit.pk) for limit in risk_customer_limits)}",
                            "name": _("Triggered Risk Customer Limits"),
                        }
                    )
                if business_customer_limits:
                    data.append(
                        {
                            "link": reverse(
                                "admin:limits_businesscustomerlimit_changelist"
                            )
                            + f"?id__in={','.join(str(limit.customer_limit.pk) for limit in business_customer_limits)}",
                            "name": _("Triggered Business Customer Limits"),
                        }
                    )

        triggered_wallet_limit_ids = list(
            LimitAlert.objects.filter(
                transaction_id=obj.id,
                merchant_limit__wallet_id=obj.wallet.wallet.pk,
            )
            .values_list("merchant_limit_id", flat=True)
            .distinct()
        )

        if triggered_wallet_limit_ids:
            wallet_ids_param = ",".join(str(pk) for pk in triggered_wallet_limit_ids)
            wallet_limits_link = (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={wallet_ids_param}"
            )
            data.append(
                {
                    "link": wallet_limits_link,
                    "name": _("Triggered Wallet Limits"),
                }
            )

        triggered_merchant_limit_ids = list(
            LimitAlert.objects.filter(
                transaction_id=obj.id,
                merchant_limit__merchant_id=obj.wallet.wallet.merchant.pk,
            )
            .values_list("merchant_limit_id", flat=True)
            .distinct()
        )

        if triggered_merchant_limit_ids:
            merchant_ids_param = ",".join(
                str(pk) for pk in triggered_merchant_limit_ids
            )
            merchant_limits_link = (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={merchant_ids_param}"
            )
            data.append(
                {
                    "link": merchant_limits_link,
                    "name": _("Triggered Merchant Limits"),
                }
            )
        if triggered_wallet_limit_ids or triggered_merchant_limit_ids:
            data.append(
                {
                    "link": reverse("admin:limits_limitalert_changelist")
                    + f"?transaction__id__exact={obj.id}",
                    "name": _("Triggered Limit Alerts"),
                }
            )

        return make_links(data)

    def has_change_permission(self, request, obj=None):
        return not settings.IS_PRODUCTION

    @admin.display(description=_("Decline Reason"))
    def decline_reason_display(self, obj: PaymentTransaction) -> str:
        if obj.decline_reason and obj.decline_code == "limit_exceeded":
            alerts = LimitAlert.objects.filter(transaction=obj)
            links = []
            for alert in alerts:
                if alert.customer_limit:
                    if alert.customer_limit.category == LimitCategory.RISK:
                        link = reverse(
                            "admin:limits_riskcustomerlimit_change",
                            args=[alert.customer_limit.pk],
                        )
                    else:
                        link = reverse(
                            "admin:limits_businesscustomerlimit_change",
                            args=[alert.customer_limit.pk],
                        )
                    links.append((link, f"Risk Customer Limit: {alert.customer_limit.description}"))
                elif alert.merchant_limit:
                    if alert.merchant_limit.category == LimitCategory.RISK:
                        link = reverse(
                            "admin:limits_riskmerchantlimit_change",
                            args=[alert.merchant_limit.pk],
                        )
                    else:
                        link = reverse(
                            "admin:limits_businessmerchantlimit_change",
                            args=[alert.merchant_limit.pk],
                        )
                    links.append((link, f"Business Merchant Limit: {alert.merchant_limit.description}"))
            if links:
                return format_html_join(" / ", "<a href='{}'>{}</a>", links)
            return obj.decline_reason
        return obj.decline_reason or "-"

    @admin.display(description=_("Limit Alerts"))
    def limit_alerts(self, obj: PaymentTransaction) -> str:
        alerts = LimitAlert.objects.filter(transaction=obj)
        links = [
            (
                reverse("admin:limits_limitalert_change", args=[alert.pk]),
                f"Alert #{alert.id} ({'Critical' if alert.is_critical else 'Regular'})",
            )
            for alert in alerts
        ]
        return format_html_join(" / ", "<a href='{}'>{}</a>", links) if links else "-"


@admin.register(models.PaymentTransactionEventLog)
class PaymentTransactionEventLogAdmin(BaseRozertAdmin):
    paginator = DisabledPaginator
    show_full_result_count = False

    list_display = [
        "id",
        "created_at",
        "event_type",
        "description",
        "transaction",
        "links",
        "public_extra",
        "request_id",
        "incoming_callback_id",
    ]
    search_fields = [
        "transaction__id",
        "description",
        "extra",
    ]
    list_filter = [
        "event_type",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "links",
        "transaction",
        "incoming_callback",
        "trace",
        "extra_f",
    ]
    exclude = ["extra"]
    ordering = ["-id"]
    list_select_related = [
        "transaction",
    ]

    def get_queryset(self, request):
        return models.PaymentTransactionEventLog.objects.order_by("-id")

    @mark_safe
    def extra_f(self, obj: models.PaymentTransactionEventLog) -> str:
        s = json.dumps(obj.extra, indent=2)
        return f"<pre>{s}</pre>"

    @mark_safe
    def trace(self, obj: models.PaymentTransactionEventLog) -> str:
        trace = obj.extra.get("trace")
        if trace:
            return f"<pre>{trace}</pre>"
        return "-"

    @mark_safe
    def public_extra(self, obj: models.PaymentTransactionEventLog) -> str:
        if obj.event_type in [
            const.EventType.ERROR,
        ]:
            return f"<pre>{json.dumps(obj.extra, indent=2)}</pre>"
        if obj.event_type == const.EventType.EXTERNAL_API_REQUEST:
            request = obj.extra["request"]
            url = request["url"].split("?")[0]
            response = obj.extra.get(
                "response",
                {
                    "status_code": None,
                },
            )
            return f"{request['method']} {url}: {response and response['status_code']}"

        return obj.extra

    def get_fields(self, request, obj=None):
        fields = ty.cast(list, super().get_fields(request, obj))

        if not request.user.is_superuser:
            fields.remove("transaction")
        return fields

    def links(self, obj: models.PaymentTransactionEventLog) -> str:
        data: list[LinkItem] = [
            {
                "link": f"/admin/payment/paymenttransaction/?id={obj.transaction_id}",
                "name": "Transaction",
            },
        ]
        return make_links(data)

    def has_change_permission(self, request, obj=None):
        return False
