import typing as ty
from decimal import Decimal

from django.db import transaction
from rozert_pay.common import const
from rozert_pay.common.const import PaymentSystemType, TransactionType
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services import db_services, event_logs
from rozert_pay.payment.systems.bitso_spei.bitso_spei_const import (
    BITSO_CLAVE_RASTREO_FIELD,
    BITSO_SPEI_IS_PAYOUT_REFUNDED,
    BITSO_SPEI_PAYOUT_REFUND_DATA,
)
from rozert_pay.payment.systems.bitso_spei.models import BitsoTransactionExtraData


@transaction.atomic
def process_bitso_spei_refund(
    *,
    refund_data: dict[str, ty.Any],
) -> PaymentTransaction:
    bitso_extra = BitsoTransactionExtraData.objects.get(
        clave_rastreo=refund_data["payload"]["details"]["clave_rastreo"],
        transaction__type=const.TransactionType.WITHDRAWAL,
    )
    trx = db_services.get_transaction(
        for_update=True, trx_id=bitso_extra.transaction_id
    )

    assert BITSO_SPEI_PAYOUT_REFUND_DATA not in trx.extra, "Refund data already exists"
    assert (
        BITSO_SPEI_IS_PAYOUT_REFUNDED not in trx.extra
    ), "Transaction already marked as refunded"

    trx.extra[BITSO_SPEI_IS_PAYOUT_REFUNDED] = True
    trx.extra[BITSO_SPEI_PAYOUT_REFUND_DATA] = refund_data
    trx.save()

    event_logs.create_transaction_log(
        trx_id=trx.id,
        event_type=const.EventType.PAYOUT_REFUND,
        description="Payout refund received",
        extra={
            "refund_data": refund_data,
        },
    )
    return trx


def get_payout_transaction_by_clave_rastreo(
    clave_rastreo: str, amount: Decimal
) -> "db_services.LockedTransaction":
    # Используем частичный индекс BITSO_SPEI_PAYOUT_LOOKUP_INDEX_NAME
    assert amount > 0
    trx = PaymentTransaction.objects.select_for_update(of=("self",)).get(
        # Индекс: BITSO_SPEI_PAYOUT_LOOKUP_INDEX_NAME
        system_type=PaymentSystemType.BITSO_SPEI,
        **{
            f"extra__{BITSO_CLAVE_RASTREO_FIELD}__iexact": clave_rastreo,
        },
        extra__has_key=BITSO_CLAVE_RASTREO_FIELD,
        type=TransactionType.WITHDRAWAL,
        amount=amount,
    )
    return ty.cast("db_services.LockedTransaction", trx)
