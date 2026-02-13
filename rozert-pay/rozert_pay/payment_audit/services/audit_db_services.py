import datetime
import json

from rozert_pay.common.metrics import track_duration
from rozert_pay.payment import models as payment_models
from rozert_pay.payment import types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment_audit.models import DBAuditItem


class DbAuditItemManager:
    @classmethod
    @track_duration("DbAuditItemManager.get_last_item")
    def get_last_item(cls, wallet_id: types.WalletId) -> DBAuditItem | None:
        # Uses index idx_dbaudit_wt_id
        return DBAuditItem.objects.filter(wallet_id=wallet_id).order_by("-id").last()

    @classmethod
    @track_duration("DbAuditItemManager.build")
    def build(
        cls,
        *,
        operation_time: datetime.datetime,
        transaction_id: types.TransactionId,
        wallet_id: types.WalletId,
        remote_status: RemoteTransactionStatus,
        system_type: str,
    ) -> "DBAuditItem":
        return DBAuditItem(
            operation_time=operation_time,
            system_type=system_type,
            wallet_id=wallet_id,
            transaction_id=transaction_id,
            operation_status=remote_status.operation_status,
            extra={
                "remote_status": json.loads(remote_status.model_dump_json()),
            },
        )

    @classmethod
    @track_duration("DbAuditItemManager.get_current_audit_item")
    def get_current_audit_item(
        cls,
        trx: "payment_models.PaymentTransaction",
    ) -> RemoteTransactionStatus | None:
        db_item: DBAuditItem | None = (
            DBAuditItem.objects.filter(
                transaction=trx,
            )
            .order_by("id")
            .last()
        )
        if not db_item:
            return None

        return RemoteTransactionStatus(**db_item.extra["remote_status"])
