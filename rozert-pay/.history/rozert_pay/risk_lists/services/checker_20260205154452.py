from __future__ import annotations

import logging
import typing as ty
from time import perf_counter
from typing import Mapping

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rozert_pay.common import const
from rozert_pay.common.metrics import RISK_REPO_QUERY_DURATION, track_duration
from rozert_pay.payment import models as payment_models
from rozert_pay.payment import types as payment_types
from rozert_pay.payment.services import db_services, event_logs
from rozert_pay.risk_lists import models as risk_models
from rozert_pay.risk_lists.const import ListType, OperationType, Scope
from rozert_pay.risk_lists.types import RiskCheckResult, RiskDecision

from .match_data import MatchData

logger = logging.getLogger(__name__)

if ty.TYPE_CHECKING:
    from rozert_pay.payment.systems.base_controller import PaymentSystemController


_LIST_TYPE_PRIORITY: Mapping[ListType, int] = {
    ListType.MERCHANT_BLACK: 0,
    ListType.WHITE: 1,
    ListType.BLACK: 2,
    ListType.GRAY: 3,
}
_PARTICIPATION_PRIORITY: Mapping[Scope, int] = {
    Scope.WALLET: 0,
    Scope.MERCHANT: 1,
    Scope.GLOBAL: 2,
}


@track_duration("risk_lists.checker.check_risk_lists_and_maybe_decline_transaction")
def check_risk_lists_and_maybe_decline_transaction(
    trx: payment_models.PaymentTransaction,
    controller: "PaymentSystemController[ty.Any, ty.Any]",
) -> bool:
    """
    Run risk-list checks and apply DECLINE side-effects if needed.
    On DECLINE, this function atomically fails the transaction and refreshes trx from DB.
    """
    result = _process_transaction(trx)

    if not result.is_declined:
        return False
    assert result.decision, "Decision is required when is_declined is True"

    # Atomic decline to avoid race conditions on pending
    with transaction.atomic():
        locked_trx = db_services.get_transaction(for_update=True, trx_id=trx.id)
        if locked_trx.status == const.TransactionStatus.PENDING:
            controller.fail_transaction(
                trx=locked_trx,
                decline_code=const.TransactionDeclineCodes.RISK_DECLINE,
                decline_reason=result.decision.value,
            )
        else:
            raise ValueError(
                f"Unexpected transaction status for risk decline: "
                f"trx_id={locked_trx.id}, status={locked_trx.status}, "
                f"expected={const.TransactionStatus.PENDING}"
            )

    trx.refresh_from_db()
    return True


@track_duration("risk_lists.checker.is_customer_in_list")
def is_customer_in_list(customer: payment_models.Customer, list_type: ListType) -> bool:
    return risk_models.RiskListEntry.objects.filter(
        customer=customer,
        list_type=list_type,
    ).exists()


@track_duration("risk_lists.checker._process_transaction")
def _process_transaction(trx: payment_models.PaymentTransaction) -> RiskCheckResult:
    """
    Single-pass matcher:
      - fetch scoped active entries for trx.operation_type,
      - sort by business priority,
      - for each entry, run MatchData.matches(),
      - on first match: return action/reason; on DECLINE — write event log here.
    """
    data = MatchData.from_transaction(trx)
    entries = _get_active_entries(
        currency_wallet=trx.wallet, transaction_type=const.TransactionType(trx.type)
    )
    entries.sort(key=_sort_key)

    for entry in entries:
        list_type = ListType(entry.list_type)
        scope = Scope(entry.scope)

        if not data.matches(entry):
            continue

        if list_type == ListType.MERCHANT_BLACK:
            decision = RiskDecision.MERCHANT_BLACKLIST
            _log_decline(
                trx_id=trx.id,
                entry_id=entry.id,
                list_type=list_type,
                decision=decision,
            )
            return RiskCheckResult(is_declined=True, decision=decision)

        if list_type == ListType.WHITE:
            logger.info(
                f"Transaction allow by whitelist: trx_id={trx.id}, entry_id={entry.id}, "
                f"list_type={list_type.value}, participation={scope.value}",
                extra={
                    "event": RiskDecision.WHITELIST.value,
                    "trx_id": trx.id,
                    "entry_id": entry.id,
                    "list_type": list_type.value,
                    "participation": scope.value,
                },
            )
            return RiskCheckResult(
                is_declined=False,
                decision=RiskDecision.WHITELIST,
            )

        if list_type == ListType.BLACK:
            decision = (
                RiskDecision.GLOBAL_BLACKLIST
                if scope == Scope.GLOBAL
                else RiskDecision.BLACKLIST
            )
            _log_decline(
                trx_id=trx.id,
                entry_id=entry.id,
                list_type=list_type,
                decision=decision,
            )
            return RiskCheckResult(is_declined=True, decision=decision)

        if list_type == ListType.GRAY:
            decision = (
                RiskDecision.GLOBAL_GRAYLIST
                if scope == Scope.GLOBAL
                else RiskDecision.GRAYLIST
            )
            logger.info(
                f"Transaction graylist flag: trx_id={trx.id}, entry_id={entry.id}, "
                f"list_type={list_type.value}, participation={scope.value}",
                extra={
                    "event": decision.value,
                    "trx_id": trx.id,
                    "entry_id": entry.id,
                    "list_type": list_type.value,
                    "participation": scope.value,
                },
            )
            return RiskCheckResult(is_declined=False, decision=decision)

    return RiskCheckResult(is_declined=False)


@track_duration("risk_lists.checker._sort_key")
def _sort_key(entry: risk_models.RiskListEntry) -> tuple[int, int, int]:
    lt = ListType(entry.list_type)
    pt = Scope(entry.scope)
    return (
        _LIST_TYPE_PRIORITY.get(lt, 99),
        _PARTICIPATION_PRIORITY.get(pt, 99),
        entry.id or 0,
    )


@track_duration("risk_lists.checker._get_active_entries")
def _get_active_entries(
    currency_wallet: payment_models.CurrencyWallet | None,
    transaction_type: const.TransactionType,
) -> list[risk_models.RiskListEntry]:
    """
    One DB read of 'active' entries for this transaction's operation_type,
    prefiltered by scope:
      (GLOBAL) OR (MERCHANT & merchant_id) OR (WALLET & wallet_id)
    """
    try:
        op = OperationType(transaction_type)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported transaction type for risk filtering: {transaction_type!r}"
        ) from exc

    now = timezone.now()

    wallet = currency_wallet.wallet if currency_wallet else None
    merchant_id = wallet.merchant_id if wallet else None
    wallet_id = currency_wallet.wallet_id if currency_wallet else None

    scope_q = Q(scope=Scope.GLOBAL)
    if merchant_id is not None:
        scope_q |= Q(
            scope=Scope.MERCHANT,
            merchant_id=merchant_id,
        )
    if wallet_id is not None:
        scope_q |= Q(
            participation_type=Scope.WALLET,
            wallet_id=wallet_id,
        )
    t0 = perf_counter()
    entries = list(
        risk_models.RiskListEntry.objects.filter(is_deleted=False)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .filter(Q(operation_type=OperationType.ALL) | Q(operation_type=op))
        .filter(scope_q)
    )
    RISK_REPO_QUERY_DURATION.labels(name="risk.get_active_entries").observe(
        perf_counter() - t0
    )
    return entries


@track_duration("risk_lists.checker._log_decline")
def _log_decline(
    *,
    trx_id: payment_types.TransactionId,
    entry_id: int | None,
    list_type: ListType,
    decision: RiskDecision,
) -> None:
    event_logs.create_transaction_log(
        trx_id=trx_id,
        event_type=const.EventType.DECLINED_BY_RISK_LIST,
        description=f"Transaction {trx_id} declined by risk list: {decision.value}",
        extra={"matched_entry_id": entry_id, "list_type": list_type.value},
    )
