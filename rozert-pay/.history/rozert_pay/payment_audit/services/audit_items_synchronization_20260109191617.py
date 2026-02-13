import datetime
import logging
import typing as ty
from datetime import timedelta

from django.utils import timezone
from rozert_pay.common.const import TransactionStatus
from rozert_pay.payment import models as payment_models
from rozert_pay.payment import types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.factories import get_payment_system_controller_by_type
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services import errors
from rozert_pay.payment.types import T_Credentials
from rozert_pay.payment_audit.models.audit_item import DBAuditItem
from rozert_pay.payment_audit.services.audit_db_services import DbAuditItemManager

logger = logging.getLogger(__name__)


class AuditItem(RemoteTransactionStatus):
    operation_time: datetime.datetime
    transaction_id: types.TransactionId


class AuditItemsSynchronizationClientMixin(ty.Generic[T_Credentials]):
    credentials_cls: type[T_Credentials]

    @classmethod
    def get_audit_items(
        cls, start: datetime.datetime, end: datetime.datetime, creds: T_Credentials
    ) -> list[AuditItem]:
        raise NotImplementedError


def synchronize_audit_items_for_wallet(
    client_cls: type[AuditItemsSynchronizationClientMixin[ty.Any]],
    wallet: "payment_models.Wallet",
    start: datetime.datetime | None = None,
    end: datetime.datetime | None = None,
) -> None:
    """
    start - if empty, last processed item operation time will be used, or now - 1h
    end - if empty, now will be used
    """
    last_item = DbAuditItemManager.get_last_item(wallet_id=wallet.id)
    start = start or timezone.now() - timedelta(hours=12)

    if last_item:
        start = max(start, last_item.operation_time)

    end = end or timezone.now()

    try:
        audit_items = client_cls.get_audit_items(
            start=start,
            end=end,
            creds=client_cls.credentials_cls(**wallet._credentials),
        )
    except Exception:
        logger.exception("Unable to get audit items")
        return

    batch = []

    existing_transaction_ids = {
        i
        for i in PaymentTransaction.objects.filter(
            id__in={item.transaction_id for item in audit_items}
        ).values_list("id", flat=True)
    }

    for item in audit_items:
        if item.transaction_id not in existing_transaction_ids:
            logger.warning(f"Unknown audit item: {item.model_dump()}")
            continue

        batch.append(
            DbAuditItemManager.build(
                operation_time=item.operation_time,
                transaction_id=item.transaction_id,
                wallet_id=wallet.id,
                remote_status=item,
                system_type=wallet.system.type,
            )
        )

    DBAuditItem.objects.bulk_create(
        batch,
        ignore_conflicts=True,
    )


def get_transaction_status(
    trx: PaymentTransaction,
) -> RemoteTransactionStatus | errors.Error:
    controller = get_payment_system_controller_by_type(trx.system_type)
    assert controller

    assert issubclass(controller.client_cls, AuditItemsSynchronizationClientMixin)

    if i := DbAuditItemManager.get_current_audit_item(trx):
        if trx.status == i.operation_status:
            return i

    synchronize_audit_items_for_wallet(
        client_cls=controller.client_cls,
        wallet=trx.wallet.wallet,
        start=trx.created_at,
        end=trx.created_at + timedelta(hours=24),
    )
    if i := DbAuditItemManager.get_current_audit_item(trx):
        return i

    return RemoteTransactionStatus(
        operation_status=TransactionStatus.PENDING,
        raw_data={
            "message": "Not a real response! No data found in payment provider yet",
        },
    )
