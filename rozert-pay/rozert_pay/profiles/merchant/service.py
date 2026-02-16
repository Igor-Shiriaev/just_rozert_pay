from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone
from rozert_pay.account.models import User
from rozert_pay.account.serializers import SessionRole, SessionRoleData
from rozert_pay.common import const
from rozert_pay.limits import const as limit_const
from rozert_pay.limits.models import MerchantLimit
from rozert_pay.payment.models import CurrencyWallet, Merchant, PaymentTransaction
from rozert_pay.payment.services.merchant_status import get_latest_status_change
from rozert_pay.profiles.merchant import dto
from rozert_pay.risk_lists import const as risk_list_const
from rozert_pay.risk_lists.models import RiskListEntry


def get_accessible_merchants_queryset(
    *,
    user: User,
    session_role: SessionRoleData,
) -> QuerySet[Merchant]:
    if user.is_superuser:
        return Merchant.objects.all()

    if session_role.logged_in_as == SessionRole.MERCHANT:
        assert session_role.merchant_id
        return Merchant.objects.filter(
            id=session_role.merchant_id,
            login_users=user,
        )

    assert session_role.merchant_group_id
    return Merchant.objects.filter(
        merchant_group_id=session_role.merchant_group_id,
        merchant_group__user=user,
    )


def get_admin_accessible_merchants_queryset(
    *,
    user: User,
) -> QuerySet[Merchant]:
    if not user.is_authenticated:
        return Merchant.objects.none()

    if user.is_superuser:
        return Merchant.objects.all()

    return Merchant.objects.filter(
        Q(login_users=user) | Q(merchant_group__user=user)
    ).distinct()


def build_merchant_info(*, merchant: Merchant) -> dto.MerchantInfo:
    last_transaction_at = (
        PaymentTransaction.objects.filter(wallet__wallet__merchant=merchant)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )

    latest_operational_change = get_latest_status_change(
        merchant=merchant, status_type="operational",
    )
    latest_risk_change = get_latest_status_change(
        merchant=merchant,
        status_type="risk",
    )

    last_status_change_at = None
    if latest_operational_change is not None:
        last_status_change_at = latest_operational_change.changed_at
    if (
        latest_risk_change is not None
        and (
            last_status_change_at is None
            or latest_risk_change.changed_at > last_status_change_at
        )
    ):
        last_status_change_at = latest_risk_change.changed_at

    operational_status_code = const.MerchantOperationalStatus(merchant.operational_status)
    operational_status = dto.MerchantOperationalStatus(
        code=operational_status_code,
        reason_code=(
            latest_operational_change.reason_code
            if (
                latest_operational_change is not None
                and operational_status_code != const.MerchantOperationalStatus.ACTIVE
            )
            else None
        ),
        comment=(
            latest_operational_change.comment
            if (
                latest_operational_change is not None
                and operational_status_code != const.MerchantOperationalStatus.ACTIVE
            )
            else None
        ),
        set_at=(
            latest_operational_change.changed_at
            if (
                latest_operational_change is not None
                and operational_status_code != const.MerchantOperationalStatus.ACTIVE
            )
            else None
        ),
    )
    risk_status = dto.MerchantRiskStatus(
        code=const.MerchantRiskStatus(merchant.risk_status),
        reason_code=(
            latest_risk_change.reason_code if latest_risk_change is not None else None
        ),
        comment=(latest_risk_change.comment if latest_risk_change is not None else None),
        set_at=(latest_risk_change.changed_at if latest_risk_change is not None else None),
    )

    return dto.MerchantInfo(
        id=str(merchant.id),
        display_name=merchant.name,
        created_at=merchant.created_at,
        status=dto.MerchantStatus(
            operational=operational_status,
            risk=risk_status,
        ),
        links=dto.MerchantLinks(
            operations_history=f"/backoffice/transactions?merchant_id={merchant.id}",
            audit_trail=f"/backoffice/audit?merchant_id={merchant.id}",
            create_limit=f"/admin/limits/merchantlimit/add/?merchant={merchant.id}",
            create_wallet_transfer=f"/backoffice/transfers?merchant_id={merchant.id}",
            reports=f"/backoffice/reports/balance?merchant_id={merchant.id}",
        ),
        last_status_change_at=last_status_change_at,
        last_transaction_at=last_transaction_at,
    )


def build_merchant_profile(*, merchant: Merchant, user: User) -> dto.MerchantProfileDto:
    currency_wallets = list(
        CurrencyWallet.objects.select_related("wallet__system")
        .filter(wallet__merchant=merchant)
        .order_by("wallet_id", "currency")
    )

    currencies = _build_aggregated_balances(currency_wallets=currency_wallets)
    wallets = _build_wallets(currency_wallets=currency_wallets)
    limits = _build_limits(merchant=merchant, user=user)
    client_lists = _build_client_lists(merchant=merchant)

    merchant_info = build_merchant_info(merchant=merchant)

    return dto.MerchantProfileDto(
        merchant=merchant_info,
        balances=dto.MerchantBalances(
            currencies=currencies,
            data_status="READY",
        ),
        wallets=wallets,
        limits=limits,
        client_lists=client_lists,
        balance_reports=dto.BalanceReports(
            actions=dto.BalanceReportAction(
                request_report=f"/backoffice/reports/balance?merchant_id={merchant.id}"
            ),
            items=[],
        ),
        transfers=dto.Transfers(
            actions=dto.TransferActions(
                create_request=f"/backoffice/transfers?merchant_id={merchant.id}"
            ),
            requests=[],
        ),
    )


def _build_aggregated_balances(
    *, currency_wallets: list[CurrencyWallet]
) -> list[dto.CurrencyBalance]:
    by_currency: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {
            "available": Decimal("0"),
            "pending": Decimal("0"),
            "frozen": Decimal("0"),
            "total": Decimal("0"),
        }
    )
    for wallet in currency_wallets:
        item = by_currency[wallet.currency]
        item["available"] += wallet.available_balance
        item["pending"] += wallet.pending_balance
        item["frozen"] += wallet.frozen_balance
        item["total"] += wallet.operational_balance

    result: list[dto.CurrencyBalance] = []
    for currency, values in sorted(by_currency.items()):
        result.append(
            dto.CurrencyBalance(
                currency=currency,
                available=_decimal_to_str(values["available"]),
                pending=_decimal_to_str(values["pending"]),
                frozen=_decimal_to_str(values["frozen"]),
                total=_decimal_to_str(values["total"]),
            )
        )
    return result


def _build_wallets(*, currency_wallets: list[CurrencyWallet]) -> list[dto.WalletInfo]:
    result: list[dto.WalletInfo] = []
    for currency_wallet in currency_wallets:
        wallet = currency_wallet.wallet
        result.append(
            dto.WalletInfo(
                wallet_id=str(wallet.id),
                currency=currency_wallet.currency,
                balances=dto.WalletBalances(
                    available=_decimal_to_str(currency_wallet.available_balance),
                    pending=_decimal_to_str(currency_wallet.pending_balance),
                    locked=_decimal_to_str(currency_wallet.frozen_balance),
                ),
                status="ACTIVE",
                links=dto.WalletLinks(
                    wallet_card=f"/admin/payment/wallet/{wallet.id}/change/",
                    wallet_operations=(
                        "/admin/payment/paymenttransaction/"
                        f"?wallet__wallet__id__exact={wallet.id}"
                    ),
                ),
                related=dto.WalletRelated(
                    terminal_id=None,
                    payment_method=wallet.system.name,
                ),
            )
        )
    return result


def _build_limits(*, merchant: Merchant, user: User) -> list[dto.LimitInfo]:
    limits_qs = (
        MerchantLimit.objects.select_related("merchant", "wallet")
        .filter(Q(merchant=merchant) | Q(wallet__merchant=merchant))
        .order_by("-created_at")
    )

    result: list[dto.LimitInfo] = []
    for limit in limits_qs:
        threshold_value = _resolve_limit_threshold(limit)
        result.append(
            dto.LimitInfo(
                limit_id=str(limit.id),
                type=limit.limit_type,
                scope=_map_limit_scope(limit.scope),
                period=_map_limit_period(limit.period),
                threshold=threshold_value,
                usage=dto.LimitUsage(
                    used="0",
                    remaining=threshold_value,
                    utilization_percent=0.0,
                ),
                action_on_exceed="BLOCK" if limit.decline_on_exceed else "NOTIFY",
                status="ACTIVE" if limit.active else "PAUSED",
                meta=dto.LimitMeta(
                    created_at=limit.created_at,
                    created_by="system",
                    comment=limit.description or None,
                ),
                links=dto.LimitLinks(
                    detail=f"/admin/limits/merchantlimit/{limit.id}/change/",
                    edit=(
                        f"/admin/limits/merchantlimit/{limit.id}/change/"
                        if user.is_superuser
                        else None
                    ),
                ),
                inherited_from=(
                    f"merchant:{limit.wallet.merchant_id}"
                    if limit.wallet_id is not None
                    else None
                ),
            )
        )
    return result


def _build_client_lists(*, merchant: Merchant) -> list[dto.ClientListEntry]:
    entries = (
        RiskListEntry.objects.select_related("customer", "wallet")
        .filter(Q(merchant=merchant) | Q(wallet__merchant=merchant))
        .order_by("-created_at")
    )

    now = timezone.now()
    result: list[dto.ClientListEntry] = []
    for entry in entries:
        if entry.is_deleted:
            status = "REMOVED"
        elif entry.expires_at is not None and entry.expires_at <= now:
            status = "EXPIRED"
        else:
            status = "ACTIVE"

        list_type = _map_list_type(entry.list_type)
        source = "MANUAL" if entry.added_by_id else "AUTO_RULE"
        result.append(
            dto.ClientListEntry(
                entry_id=str(entry.id),
                client_id=_resolve_client_id(entry),
                list_type=list_type,
                reason_code=entry.reason or "UNSPECIFIED",
                source=source,
                added_at=entry.created_at,
                status=status,
                comment=entry.delete_reason,
                expires_at=entry.expires_at,
                links=dto.ClientListLinks(client_card=None),
            )
        )
    return result


def _decimal_to_str(value: Decimal) -> str:
    return f"{value:.2f}"


def _resolve_limit_threshold(limit: MerchantLimit) -> str:
    numeric_fields: list[Any] = [
        limit.max_operations,
        limit.max_overall_decline_percent,
        limit.max_withdrawal_decline_percent,
        limit.max_deposit_decline_percent,
        limit.min_amount,
        limit.max_amount,
        limit.total_amount,
        limit.max_ratio,
        limit.burst_minutes,
    ]
    for value in numeric_fields:
        if value is not None:
            if isinstance(value, Decimal):
                return _decimal_to_str(value)
            return str(value)
    return "0"


def _map_limit_scope(scope: str) -> str:
    if scope == "merchant":
        return "MERCHANT"
    if scope == "wallet":
        return "WALLET"
    return "TERMINAL"


def _map_limit_period(period: str | None) -> dto.LimitPeriod:
    if period is None:
        return dto.LimitPeriod(type="ROLLING", window=None)
    if period == limit_const.LimitPeriod.BEGINNING_OF_DAY:
        return dto.LimitPeriod(type="DAY", window="fixed")
    if period == limit_const.LimitPeriod.BEGINNING_OF_HOUR:
        return dto.LimitPeriod(type="ROLLING", window="1H")
    if period == limit_const.LimitPeriod.TWENTY_FOUR_HOURS:
        return dto.LimitPeriod(type="ROLLING", window="24H")
    if period == limit_const.LimitPeriod.ONE_HOUR:
        return dto.LimitPeriod(type="ROLLING", window="1H")
    return dto.LimitPeriod(type="ROLLING", window=period)


def _map_list_type(list_type: str) -> str:
    if list_type == risk_list_const.ListType.GRAY:
        return "GREY"
    return str(list_type)


def _resolve_client_id(entry: RiskListEntry) -> str:
    if entry.customer_id and entry.customer:
        return entry.customer.external_id
    if entry.customer_wallet_id:
        return entry.customer_wallet_id
    if entry.email:
        return entry.email
    if entry.phone:
        return entry.phone
    if entry.ip:
        return entry.ip
    return f"entry-{entry.id}"
