import traceback
import typing as ty

from bm.django_utils.middleware import get_request_id
from rozert_pay.common import const
from rozert_pay.common.metrics import track_duration
from rozert_pay.payment import models, types
from rozert_pay.payment.models import EventLog


@track_duration("event_logs.create_event_log")
def create_event_log(
    *,
    event_type: const.EventType,
    description: str,
    extra: dict[str, ty.Any],
    system_type: const.PaymentSystemType,
    merchant_id: types.MerchantID | None,
    customer_id: types.CustomerId | None = None,
) -> models.EventLog:
    return EventLog.objects.create(
        event_type=event_type,
        description=description,
        extra=extra,
        system_type=system_type,
        merchant_id=merchant_id,
        customer_id=customer_id,
        request_id=get_request_id(),
    )


@track_duration("event_logs.create_transaction_log")
def create_transaction_log(
    *,
    trx_id: types.TransactionId,
    event_type: const.EventType,
    description: str,
    extra: dict[str, ty.Any],
    trace: bool = False,
) -> models.PaymentTransactionEventLog:
    if trace:
        extra["trace"] = traceback.format_exc(limit=30)
    return models.PaymentTransactionEventLog.objects.create(
        transaction_id=trx_id,
        event_type=event_type,
        extra=extra,
        description=description,
        request_id=get_request_id(),
    )
