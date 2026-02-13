import typing as ty

from django.contrib import admin
from rozert_pay.common.helpers import admin_utils
from rozert_pay.payment import models
from rozert_pay.payment.admin.merchant import BaseRozertAdmin


@admin.register(models.PaymentSystem)
class PaymentSystemAdmin(BaseRozertAdmin):
    list_display = [
        "id",
        "name",
        "slug",
        "created_at",
        "updated_at",
        "links",
    ]
    search_fields = ["name", "id"]
    readonly_fields = ["links"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        result = super().get_form(request, obj, change, **kwargs)

        # Sort types
        if "type" in result.base_fields:
            ty.cast(ty.Any, result.base_fields["type"]).choices.__dict__[
                "choices"
            ].sort(key=lambda i: i[1])

        return result

    def links(self, obj: models.PaymentSystem) -> str:
        data: list[admin_utils.LinkItem] = [
            {
                "link": f"/admin/payment/incomingcallback/?system_id={obj.id}",
                "name": "Incoming Callbacks",
            },
            {
                "link": f"/admin/payment/wallet/?system_id={obj.id}",
                "name": "Wallets",
            },
            {
                "link": f"/admin/payment/paymenttransaction?wallet__wallet__system_id={obj.id}",
                "name": "Transactions",
            },
        ]

        return admin_utils.make_links(data)
