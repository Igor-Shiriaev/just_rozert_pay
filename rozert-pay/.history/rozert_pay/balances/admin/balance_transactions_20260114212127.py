from django.contrib import admin
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from rozert_pay.balances import models as balance_models
from rozert_pay.common.helpers.admin_utils import LinkItem, make_links
from rozert_pay.payment.admin.merchant import BaseRozertAdmin


@admin.register(balance_models.BalanceTransaction)
class BalanceTransactionAdmin(BaseRozertAdmin):
    list_display = [
        "short_id",
        "info",
        "links",
        "created_at",
    ]
    list_filter = ("type", "initiator", "currency_wallet__currency")
    search_fields = (
        "id__iexact",
        "currency_wallet__id__iexact",
        "payment_transaction__id__iexact",
    )
    ordering = ("-created_at",)
    list_select_related = ("currency_wallet", "payment_transaction")

    readonly_fields = [
        "id",
        "currency_wallet",
        "type",
        "amount",
        "operational_before",
        "operational_after",
        "frozen_before",
        "frozen_after",
        "pending_before",
        "pending_after",
        "payment_transaction",
        "description",
        "initiator",
        "created_at",
    ]
    fieldsets = (
        (
            _("Core Information"),
            {"fields": ("id", "created_at", "type", "initiator", "description")},
        ),
        (
            _("Wallet & Related Transaction"),
            {"fields": ("currency_wallet", "payment_transaction")},
        ),
        (_("Amount Details"), {"fields": ("amount",)}),
        (
            _("Balance Snapshots (Operational | Frozen | Pending)"),
            {
                "classes": ("collapse",),
                "fields": (
                    ("operational_before", "operational_after"),
                    ("frozen_before", "frozen_after"),
                    ("pending_before", "pending_after"),
                ),
            },
        ),
    )

    def get_queryset(self, request) -> QuerySet[balance_models.BalanceTransaction]:
        qs = super().get_queryset(request)
        return qs.select_related(
            "currency_wallet",
            "currency_wallet__wallet",
            "payment_transaction",
        )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(
        self, request, obj: balance_models.BalanceTransaction | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request, obj: balance_models.BalanceTransaction | None = None
    ) -> bool:
        return False

    @admin.display(description="ID", ordering="id")
    def short_id(self, obj: balance_models.BalanceTransaction) -> str:
        return str(obj.id).split("-")[0] + "..."

    @admin.display(description="Info")
    def info(self, obj: balance_models.BalanceTransaction) -> str:
        amount_color = "green" if obj.amount > 0 else "red"
        amount_sign = "+" if obj.amount > 0 else ""

        items = [
            f"<li>Type: <b>{obj.get_type_display()}</b></li>",
            f'<li>Amount: <b style="color: {amount_color};">{amount_sign}{obj.amount}</b></li>',
            f"<li>Balance: {obj.operational_before} → <b>{obj.operational_after}</b></li>",
            f"<li>Wallet: {obj.currency_wallet.wallet.name} ({obj.currency_wallet.currency})</li>",
            f"<li>Initiator: {obj.get_initiator_display()}</li>",
        ]
        return format_html(
            format_string='<ul style="margin:0; padding-left:15px; white-space:nowrap;">{}</ul>',
            format_html(format_string="".join(items)),
        )

    @admin.display(description="Links")
    def links(self, obj: balance_models.BalanceTransaction) -> str:
        links: list[LinkItem] = []

        links.append(
            {
                "name": _("Currency Wallet"),
                "link": reverse(
                    "admin:payment_currencywallet_change", args=[obj.currency_wallet.pk]
                ),
            }
        )

        if obj.payment_transaction:
            links.append(
                {
                    "name": _("Payment Transaction"),
                    "link": reverse(
                        "admin:payment_paymenttransaction_change",
                        args=[obj.payment_transaction.pk],
                    ),
                }
            )

        return make_links(links)
