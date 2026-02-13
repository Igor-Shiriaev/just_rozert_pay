import traceback
import typing as ty
from uuid import UUID

from bm.django_utils.middleware import get_request_id
from rozert_pay.common import const
from rozert_pay.payment import models, types
from rozert_pay.payment.models import EventLog


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


def create_routing_log(
    *,
    merchant_id: int,
    merchant_terminal_pk: int | None,
    merchant_terminal_uuid: str | UUID,
    system_type: const.PaymentSystemType | None = None,
    logs: str,
    success: bool,
    result_wallet_id: str | UUID | None = None,
) -> models.EventLog:
    extra_data = {
        "routing_trace": logs,
        "success": success,
        "terminal_uuid": str(merchant_terminal_uuid),
    }

    if result_wallet_id:
        extra_data["result_wallet_id"] = str(result_wallet_id)

    return models.EventLog.objects.create(
        event_type=const.EventType.ROUTING_DECISION,
        description=f"Routing finished. Success: {success}",
        extra=extra_data,
        merchant_id=merchant_id,
        merchant_terminal_id=merchant_terminal_pk,
        system_type=system_type,
        request_id=get_request_id(),
    )
