from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Optional

from auditlog.models import LogEntry as AuditLogEntry

if TYPE_CHECKING:
    from rozert_pay.payment.models import Merchant

StatusType = Literal["operational", "risk"]
STATUS_CHANGE_KEY = "status_change"


@dataclass(slots=True)
class MerchantStatusChangeRecord:
    status_type: StatusType
    changed_at: datetime
    from_status: Optional[str]
    to_status: Optional[str]
    reason_code: Optional[str]
    comment: Optional[str]
    actor_id: Optional[int]


def log_status_change(
    *,
    merchant: "Merchant",
    status_type: StatusType,
    from_status: Optional[str],
    to_status: Optional[str],
    reason_code: Optional[str] = None,
    comment: Optional[str] = None,
    actor: Optional[object] = None,
) -> None:
    AuditLogEntry.objects.log_create(
        instance=merchant,
        action=AuditLogEntry.Action.UPDATE,
        changes={f"{status_type}_status": [from_status, to_status]},
        additional_data={
            STATUS_CHANGE_KEY: {
                "type": status_type,
                "reason_code": reason_code,
                "comment": comment,
            }
        },
        actor=actor,
        force_log=True,
    )


def get_latest_status_change(
    merchant: "Merchant", status_type: StatusType
) -> MerchantStatusChangeRecord | None:
    entry = (
        merchant.history.filter(
            **{f"additional_data__{STATUS_CHANGE_KEY}__type": status_type}
        )
        .order_by("-timestamp")
        .first()
    )
    if not entry:
        return None

    additional = entry.additional_data or {}
    meta = additional.get(STATUS_CHANGE_KEY, {})
    changes = entry.changes_dict
    status_changes = changes.get(f"{status_type}_status") or [None, None]
    return MerchantStatusChangeRecord(
        status_type=status_type,
        changed_at=entry.timestamp,
        from_status=status_changes[0],
        to_status=status_changes[1],
        reason_code=meta.get("reason_code"),
        comment=meta.get("comment"),
        actor_id=entry.actor_id,
    )


__all__ = [
    "MerchantStatusChangeRecord",
    "StatusType",
    "get_latest_status_change",
    "log_status_change",
]
