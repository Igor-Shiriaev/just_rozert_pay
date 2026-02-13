from functools import partial
from typing import Iterable

from bm.django_utils.paginators import DisabledPaginator
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.payment import models
from rozert_pay.payment.admin.merchant import BaseRozertAdmin
from rozert_pay.payment.services import outcoming_callbacks
from rozert_pay.payment.tasks import handle_incoming_callback


@admin.register(models.IncomingCallback)
class IncomingCallbackAdmin(BaseRozertAdmin):
    list_display = [
        "id",
        "created_at",
        "system",
        "transaction",
        "ip",
        "status",
        "remote_status",
        "links",
        "error_type",
        "error",
        "updated_at",
    ]
    list_filter = [
        "status",
    ]
    search_fields = [
        "system__name",
        "system__type",
        "error",
        "id"
    ]
    readonly_fields = [
        "links",
        "created_at",
        "updated_at",
        "transaction",
        "system",
    ]
    ordering = ["-created_at"]
    actions = ["retry"]
    change_actions = ["retry"]
    paginator = DisabledPaginator
    show_full_result_count = False

    def remote_status(self, obj: models.IncomingCallback) -> str:
        return (
            obj.remote_transaction_status
            and obj.remote_transaction_status["operation_status"]
            or "-"
        )

    def retry(
        self,
        request: HttpRequest,
        queryset_or_item: QuerySet[models.IncomingCallback] | models.IncomingCallback,
    ):
        queryset: Iterable[models.IncomingCallback]
        if isinstance(queryset_or_item, models.IncomingCallback):
            queryset = [queryset_or_item]
        else:
            queryset = queryset_or_item

        for obj in queryset:
            handle_incoming_callback(obj.id, is_retry=True, retry_user=request.user)

        self.message_user(request, "Callbacks are processed")
        return

    def links(self, obj: models.IncomingCallback) -> str:
        data: list[LinkItem] = [
            {
                "link": f"/admin/payment/paymentsystem/?id={obj.system_id}",
                "name": "System",
            },
            {
                "link": f"/admin/payment/paymenttransactioneventlog/?incoming_callback_id={obj.id}",
                "name": "Logs",
            },
        ]

        if obj.transaction_id:
            data.append(
                {
                    "link": f"/admin/payment/paymenttransaction/?id={obj.transaction_id}",
                    "name": "Transaction",
                }
            )

        return make_links(data)


@admin.register(models.OutcomingCallback)
class OutcomingCallbackAdmin(BaseRozertAdmin):
    list_display = [
        "id",
        "created_at",
        "status",
        "transaction",
        "callback_type",
        "target",
        "error",
        "last_attempt_at",
        "attempt",
    ]
    ordering = ["-created_at"]
    readonly_fields = [
        "logs",
    ]
    change_actions = ["retry"]
    actions = ["retry"]
    list_filter = [
        "status",
        "callback_type",
    ]
    raw_id_fields = [
        "transaction",
    ]

    def retry(
        self,
        request,
        item_or_qs: models.OutcomingCallback | QuerySet[models.OutcomingCallback],
    ):
        outcoming_callbacks.retry_outcoming_callback(
            item_or_qs=item_or_qs,
            action_user=request.user,
            message_user=partial(self.message_user, request),
        )

    def attempt(self, obj: models.OutcomingCallback) -> str:
        return f"{obj.current_attempt}/{obj.max_attempts}"
