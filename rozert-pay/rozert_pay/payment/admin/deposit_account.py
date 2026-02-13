from django.contrib import admin
from rozert_pay.payment import models
from rozert_pay.payment.admin.merchant import BaseRozertAdmin


@admin.register(models.DepositAccount)
class DepositAccountAdmin(BaseRozertAdmin):
    pass
