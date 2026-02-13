from django.db import models
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.payment.models import PaymentTransaction


class BitsoTransactionExtraData(BaseDjangoModel):
    transaction = models.OneToOneField(PaymentTransaction, on_delete=models.CASCADE)
    clave_rastreo = models.CharField(
        max_length=64, db_index=True, verbose_name="Clave de rastreo"
    )
