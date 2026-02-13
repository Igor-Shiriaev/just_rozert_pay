from django.db import models
from rozert_pay.common import const
from rozert_pay.common.const import TransactionStatus
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.payment import types


class DBAuditItem(BaseDjangoModel):
    wallet_id: types.WalletId

    class Meta:
        verbose_name = "Audit Items"
        constraints = [
            models.UniqueConstraint(
                fields=["operation_time", "transaction"], name="uq_dbaudit_optime_trx"
            ),
        ]
        indexes = [models.Index(fields=["wallet", "-id"], name="idx_dbaudit_wt_id")]

    operation_time = models.DateTimeField()
    system_type = models.CharField(
        max_length=200, choices=const.PaymentSystemType.choices
    )
    wallet = models.ForeignKey(
        "payment.Wallet", on_delete=models.CASCADE, db_index=False
    )
    transaction = models.ForeignKey(
        "payment.PaymentTransaction", on_delete=models.CASCADE
    )
    operation_status = models.CharField(
        max_length=255, choices=TransactionStatus.choices
    )
    extra = models.JSONField()
