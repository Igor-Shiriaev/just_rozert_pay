import logging
from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Max, Min, QuerySet
from django.http import FileResponse, HttpRequest
from django.utils.translation import gettext_lazy as _
from rozert_pay.payment import models
from rozert_pay.payment.admin.merchant import BaseRozertAdmin
from rozert_pay.payment.admin.mixins import TransactionLinksMixin
from rozert_pay.payment.admin.utils import (
    TransactionDateTimeQuickFilter,
    export_transactions_as_response,
)

logger = logging.getLogger(__name__)


@admin.register(models.TransactionManager)
class TransactionManagerAdmin(TransactionLinksMixin, BaseRozertAdmin):
    export_max_rows = 10000
    list_display = [
        "id",
        "created_at",
        "updated_at",
        "type",
        "amount",
        "currency",
        "status",
        "decline_reason",
        "get_system",
        "get_merchant",
        "get_wallet",
        "links",
    ]

    list_select_related = [
        "wallet__wallet__merchant",
        "wallet__wallet__system",
    ]

    ordering = ["-created_at", "-pk"]

    search_fields = [
        "id",
        "uuid",
        "id_in_payment_system",
        "wallet__wallet__merchant__name",
        "wallet__wallet__name",
        "wallet__wallet__id",
    ]

    actions = ["export_to_xlsx"]

    list_filter = [
        ("created_at", TransactionDateTimeQuickFilter),
        "status",
        "type",
        "wallet__wallet__system__type",
        "wallet__wallet__merchant",
        "wallet__wallet",
    ]

    @admin.display(description=_("System"), ordering="wallet__wallet__system__name")
    def get_system(self, obj: models.PaymentTransaction) -> str:
        return str(obj.wallet.wallet.system.name)

    @admin.display(description=_("Merchant"), ordering="wallet__wallet__merchant__name")
    def get_merchant(self, obj: models.PaymentTransaction) -> str:
        return str(obj.wallet.wallet.merchant.name)

    @admin.display(description=_("Wallet"), ordering="wallet__wallet__name")
    def get_wallet(self, obj: models.PaymentTransaction) -> str:
        return str(obj.wallet.wallet.name)

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).select_related(*self.list_select_related)

    @admin.action(description=_("Export to XLSX"))
    def export_to_xlsx(
        self, request: HttpRequest, queryset: QuerySet
    ) -> FileResponse | None:
        if not queryset.exists():
            self.message_user(
                request,
                _("No transactions found matching the selected criteria."),
                level=messages.WARNING,
            )
            return None

        limit = self.export_max_rows
        ids = list(queryset.values_list("pk", flat=True)[: limit + 1])
        if len(ids) > self.export_max_rows:
            self.message_user(
                request,
                _(
                    f"Too many rows. Maximum allowed is {self.export_max_rows}. "
                    "Please filter by date or other fields."
                ),
                level=messages.ERROR,
            )
            return None

        export_qs = queryset.filter(pk__in=ids)
        dates = export_qs.aggregate(
            min_date=Min("created_at"), max_date=Max("created_at")
        )

        if dates["min_date"] and dates["max_date"]:
            diff = dates["max_date"] - dates["min_date"]
            if diff > timedelta(days=31, hours=1):
                self.message_user(
                    request,
                    _(
                        "Export failed: Selected period exceeds 31 days. Please use the Date filter."
                    ),
                    level=messages.ERROR,
                )
                return None

        return export_transactions_as_response(export_qs)
