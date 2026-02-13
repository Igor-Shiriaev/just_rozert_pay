from django.db import models
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.payment import types
from rozert_pay.payment.models import PaymentTransaction


class StpCodiUniqueIds(BaseDjangoModel):
    transaction = models.OneToOneField(PaymentTransaction, on_delete=models.CASCADE)


def get_or_create_unique_id(transaction_id: types.TransactionId) -> int:
    return StpCodiUniqueIds.objects.get_or_create(transaction_id=transaction_id)[0].id
