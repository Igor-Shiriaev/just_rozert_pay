from __future__ import annotations

import logging
from datetime import datetime
from typing import Sequence

from django.utils import timezone
from rozert_pay.celery_app import app
from rozert_pay.common.const import CeleryQueue
from rozert_pay.payment.systems.bitso_spei.audit import BitsoSpeiAudit

logger = logging.getLogger(__name__)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


@app.task(queue=CeleryQueue.LOW_PRIORITY, name="payment.bitso_spei.run_audit")
def run_bitso_spei_audit(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    dry_run: bool = False,
    wallet_ids: Sequence[int] | None = None,
    initiated_by: int | None = None,
) -> None:
    start_dt = _parse_datetime(start_date)
    end_dt = _parse_datetime(end_date)

    logger.info(
        "Bitso SPEI audit scheduled",
        extra={
            "start_date": start_dt,
            "end_date": end_dt,
            "dry_run": dry_run,
            "wallet_ids": list(wallet_ids) if wallet_ids else None,
            "initiated_by": initiated_by,
        },
    )

    audit = BitsoSpeiAudit(
        start_date=start_dt,
        end_date=end_dt,
        dry_run=dry_run,
    )

    audit.run()
