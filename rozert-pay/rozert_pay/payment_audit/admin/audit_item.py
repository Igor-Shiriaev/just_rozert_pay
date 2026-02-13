from django.contrib import admin
from rozert_pay.payment.admin import BaseRozertAdmin
from rozert_pay.payment_audit.models import DBAuditItem


@admin.register(DBAuditItem)
class AuditItemAdmin(BaseRozertAdmin):
    list_display = [
        "id",
        "operation_time",
        "system_type",
        "wallet",
        "transaction",
        "operation_status",
    ]
    list_filter = [
        "system_type",
    ]
    search_fields = [
        "transaction__uuid",
        "wallet__uuid",
    ]

    list_select_related = ["wallet", "transaction"]
