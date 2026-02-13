import json
import typing as ty
from datetime import timedelta
from typing import Literal, cast

from bm.django_utils.paginators import DisabledPaginator
from bm.utils import log_errors
from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from rozert_pay.account.models import User
from rozert_pay.common import const
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.limits.models import LimitAlert
from rozert_pay.payment.admin.merchant import BaseRozertAdmin
from rozert_pay.payment.admin.mixins import TransactionLinksMixin
from rozert_pay.payment.factories import get_payment_system_controller
from rozert_pay.payment.models import (
    PaymentPermissions,
    PaymentTransaction,
    PaymentTransactionEventLog,
)
from rozert_pay.payment.services.errors import Error
from rozert_pay.payment.services.transaction_actualization import (
    TransactionActualizationForm,
)
from rozert_pay.payment.systems.bitso_spei.tasks import run_bitso_spei_audit


class BitsoSpeiAuditForm(forms.Form):
    start_date = forms.DateTimeField(
        required=False,
        label=_("Start date"),
        help_text=_("Optional. Defaults to the last 24 hours."),
    )
    end_date = forms.DateTimeField(
        required=False,
        label=_("End date"),
        help_text=_("Optional. Defaults to now."),
    )
    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Dry run"),
        help_text=_("Do not make changes, only verify."),
    )

    def clean(self) -> dict[str, ty.Any]:
        data = ty.cast(dict[str, ty.Any], super().clean())
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end and start >= end:
            raise forms.ValidationError(_("Start date must be earlier than end date."))
        return data


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(TransactionLinksMixin, BaseRozertAdmin):
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
    change_list_template = "admin/payment/paymenttransaction/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "bitso-spei-audit/",
                self.admin_site.admin_view(self.bitso_spei_audit_view),
                name="payment_paymenttransaction_bitso_spei_audit",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request: HttpRequest, extra_context=None):
        extra_context = extra_context or {}
        extra_context.setdefault(
            "bitso_audit_url",
            reverse("admin:payment_paymenttransaction_bitso_spei_audit"),
        )
        extra_context.setdefault(
            "bitso_audit_label",
            _("Run Bitso SPEI audit"),
        )
        return super().changelist_view(request, extra_context=extra_context)

    def bitso_spei_audit_view(self, request: HttpRequest) -> HttpResponse:
        initial_defaults = {
            "start_date": timezone.now() - timedelta(hours=24),
            "end_date": timezone.now(),
            "dry_run": True,
        }

        if request.method == "POST":
            form = BitsoSpeiAuditForm(request.POST)
            if form.is_valid():
                cleaned = form.cleaned_data
                start = cleaned.get("start_date")
                end = cleaned.get("end_date")
                run_bitso_spei_audit.delay(
                    start_date=start.isoformat() if start else None,
                    end_date=end.isoformat() if end else None,
                    dry_run=bool(cleaned.get("dry_run")),
                    initiated_by=getattr(request.user, "pk", None),
                )
                messages.success(request, _("Bitso SPEI audit task has been queued."))
                return redirect("admin:payment_paymenttransaction_changelist")
        else:
            form = BitsoSpeiAuditForm(initial=initial_defaults)

        context = {
            **self.admin_site.each_context(request),
            "form": form,
            "title": _("Run Bitso SPEI audit"),
        }
        return render(request, "admin/bitso_spei_audit.html", context)

    @admin.action(
        description="Actualize transaction status from payment system",
        permissions=[PaymentPermissions.CAN_ACTUALIZE_TRANSACTION],
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
        permissions=[PaymentPermissions.CAN_SET_TRANSACTION_STATUS.to_permission_str()],
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
    def info(self, o: PaymentTransaction):
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

    def decline_info(self, o: PaymentTransaction):
        if o.decline_code or o.decline_reason:
            return f"{o.decline_code or '-'}: {o.decline_reason or '-'}"
        return "-"

    def lookup_allowed(self, lookup, value, request=None):
        return True

    def has_change_permission(self, request, obj=None):
        return not settings.IS_PRODUCTION

    @admin.display(description=_("Decline Reason"))
    def decline_reason_display(self, obj: PaymentTransaction) -> str:
        if obj.decline_reason and obj.decline_code == "limit_exceeded":
            alerts = LimitAlert.objects.filter(transaction=obj)
            links = []
            for alert in alerts:
                if alert.customer_limit:
                    links.append(
                        (
                            reverse(
                                "admin:limits_customerlimit_change",
                                args=[alert.customer_limit.pk],
                            ),
                            f"Customer Limit: {alert.customer_limit.description}",
                        )
                    )
                elif alert.merchant_limit:
                    links.append(
                        (
                            reverse(
                                "admin:limits_merchantlimit_change",
                                args=[alert.merchant_limit.pk],
                            ),
                            f"Merchant Limit: {alert.merchant_limit.description}",
                        )
                    )
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


@admin.register(PaymentTransactionEventLog)
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
        return super().get_queryset(request).order_by("-id")

    @mark_safe
    def extra_f(self, obj: PaymentTransactionEventLog) -> str:
        if obj.extra is None:
            return "-"
        s = json.dumps(obj.extra, indent=2)
        return f"<pre>{s}</pre>"

    @mark_safe
    def trace(self, obj: PaymentTransactionEventLog) -> str:
        if not obj.extra:
            return "-"
        trace = obj.extra.get("trace")
        if trace:
            return f"<pre>{trace}</pre>"
        return "-"

    @mark_safe
    def public_extra(self, obj: PaymentTransactionEventLog) -> str:
        if obj.extra is None:
            return "-"
        if obj.event_type in [
            const.EventType.ERROR,
        ]:
            return f"<pre>{json.dumps(obj.extra, indent=2)}</pre>"
        if obj.event_type == const.EventType.EXTERNAL_API_REQUEST:
            request = obj.extra.get("request")
            if not request:
                return f"<pre>{json.dumps(obj.extra, indent=2)}</pre>"

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

    def links(self, obj: PaymentTransactionEventLog) -> str:
        data: list[LinkItem] = [
            {
                "link": f"/admin/payment/paymenttransaction/?id={obj.transaction_id}",
                "name": "Transaction",
            },
        ]
        return make_links(data)

    def has_change_permission(self, request, obj=None):
        return False
