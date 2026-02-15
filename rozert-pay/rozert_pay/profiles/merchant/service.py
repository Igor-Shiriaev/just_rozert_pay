from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rozert_pay.common import const
from rozert_pay.limits.models.merchant_limits import MerchantLimit
from rozert_pay.payment.models import CurrencyWallet, Merchant, PaymentTransaction
from rozert_pay.profiles.merchant.dto import (
    BalanceReportAction,
    BalanceReports,
    ClientListEntry,
    ClientListLinks,
    CurrencyBalance,
    LimitInfo,
    LimitLinks,
    LimitMeta,
    LimitPeriod,
    LimitUsage,
    MerchantBalances,
    MerchantInfo,
    MerchantLinks,
    MerchantOperationalStatus,
    MerchantProfileDto,
    MerchantRiskStatus,
    MerchantStatus,
    TransferActions,
    Transfers,
    WalletBalances,
    WalletInfo,
    WalletLinks,
)
from rozert_pay.risk_lists.const import ListType
from rozert_pay.risk_lists.models import RiskListEntry


def _format_amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _limit_threshold(limit: MerchantLimit) -> str:
    checks: list[tuple[str, Decimal | int | None]] = [
        ("min_amount", limit.min_amount),
        ("max_amount", limit.max_amount),
        ("total_amount", limit.total_amount),
        ("max_operations", limit.max_operations),
        ("max_ratio", limit.max_ratio),
        ("max_overall_decline_percent", limit.max_overall_decline_percent),
        ("max_withdrawal_decline_percent", limit.max_withdrawal_decline_percent),
        ("max_deposit_decline_percent", limit.max_deposit_decline_percent),
        ("burst_minutes", limit.burst_minutes),
    ]
    for key, value in checks:
        if value is not None:
            return f"{key}={value}"
    return "not_configured"


def build_merchant_profile(*, merchant: Merchant) -> MerchantProfileDto:
    currency_wallets = list(
        CurrencyWallet.objects.select_related("wallet", "wallet__merchant").filter(
            wallet__merchant=merchant
        )
    )

    grouped_balances: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {
            "operational": Decimal("0"),
            "pending": Decimal("0"),
            "frozen": Decimal("0"),
            "available": Decimal("0"),
        }
    )
    wallet_items: list[WalletInfo] = []
    for currency_wallet in currency_wallets:
        available = currency_wallet.available_balance
        grouped_balances[currency_wallet.currency]["operational"] += (
            currency_wallet.operational_balance
        )
        grouped_balances[currency_wallet.currency]["pending"] += (
            currency_wallet.pending_balance
        )
        grouped_balances[currency_wallet.currency]["frozen"] += (
            currency_wallet.frozen_balance
        )
        grouped_balances[currency_wallet.currency]["available"] += available

        wallet_admin_link = reverse("admin:payment_wallet_change", args=[currency_wallet.wallet_id])
        transactions_link = (
            reverse("admin:payment_transactionmanager_changelist")
            + f"?wallet__wallet__id__exact={currency_wallet.wallet_id}"
        )
        wallet_items.append(
            WalletInfo(
                wallet_id=str(currency_wallet.wallet_id),
                currency=currency_wallet.currency,
                balances=WalletBalances(
                    available=_format_amount(available),
                    pending=_format_amount(currency_wallet.pending_balance),
                    locked=_format_amount(currency_wallet.frozen_balance),
                ),
                status="ACTIVE",
                links=WalletLinks(
                    wallet_card=wallet_admin_link,
                    wallet_operations=transactions_link,
                ),
            )
        )

    currency_items = [
        CurrencyBalance(
            currency=currency,
            available=_format_amount(values["available"]),
            pending=_format_amount(values["pending"]),
            frozen=_format_amount(values["frozen"]),
            total=_format_amount(values["operational"]),
        )
        for currency, values in sorted(grouped_balances.items())
    ]

    last_transaction = (
        PaymentTransaction.objects.filter(wallet__wallet__merchant=merchant)
        .order_by("-created_at")
        .first()
    )

    risk_status = (
        const.MerchantRiskStatus.GREY
        if merchant.risk_control
        else const.MerchantRiskStatus.WHITE
    )

    limits_qs = MerchantLimit.objects.select_related("merchant", "wallet").filter(
        merchant=merchant
    ) | MerchantLimit.objects.select_related("merchant", "wallet").filter(
        wallet__merchant=merchant
    )

    limit_items: list[LimitInfo] = []
    for limit in limits_qs.distinct().order_by("-created_at"):
        period_map = {
            "one_day": "DAY",
            "one_week": "WEEK",
            "one_month": "MONTH",
        }
        period_type = period_map.get(str(limit.period), "ROLLING")
        limit_items.append(
            LimitInfo(
                limit_id=str(limit.id),
                type=limit.limit_type,
                scope=limit.scope.upper(),
                period=LimitPeriod(type=period_type, window=None),
                threshold=_limit_threshold(limit),
                usage=LimitUsage(used="0.00", remaining="0.00", utilization_percent=0),
                action_on_exceed=("BLOCK" if limit.decline_on_exceed else "NOTIFY"),
                status=("ACTIVE" if limit.active else "PAUSED"),
                meta=LimitMeta(
                    created_at=limit.created_at,
                    created_by="system",
                    comment=limit.description or None,
                ),
                links=LimitLinks(
                    detail=reverse("admin:limits_merchantlimit_change", args=[limit.id]),
                    edit=reverse("admin:limits_merchantlimit_change", args=[limit.id]),
                ),
                inherited_from=(
                    f"wallet:{limit.wallet_id}" if limit.wallet_id else None
                ),
            )
        )

    list_entries: list[ClientListEntry] = []
    risk_entries = RiskListEntry.objects.select_related("customer").filter(
        merchant=merchant,
        is_deleted=False,
    )
    for risk_entry in risk_entries.order_by("-created_at")[:200]:
        if risk_entry.list_type == ListType.GRAY:
            list_type = "GREY"
        elif risk_entry.list_type == ListType.MERCHANT_BLACK:
            list_type = "BLACK"
        else:
            list_type = risk_entry.list_type

        if risk_entry.expires_at and risk_entry.expires_at < timezone.now():
            status = "EXPIRED"
        else:
            status = "ACTIVE"

        client_id = (
            risk_entry.customer.external_id
            if risk_entry.customer_id and risk_entry.customer
            else str(risk_entry.customer_id or "unknown")
        )
        list_entries.append(
            ClientListEntry(
                entry_id=str(risk_entry.id),
                client_id=client_id,
                list_type=list_type,
                reason_code=risk_entry.reason or "UNSPECIFIED",
                source=("MANUAL" if risk_entry.added_by_id else "AUTO_RULE"),
                added_at=risk_entry.created_at,
                status=status,
                comment=risk_entry.reason or None,
                expires_at=risk_entry.expires_at,
                links=ClientListLinks(client_card=None),
            )
        )

    return MerchantProfileDto(
        merchant=MerchantInfo(
            id=str(merchant.id),
            display_name=merchant.name,
            legal_name=None,
            created_at=merchant.created_at,
            status=MerchantStatus(
                operational=MerchantOperationalStatus(
                    code=const.MerchantOperationalStatus.ACTIVE
                ),
                risk=MerchantRiskStatus(code=risk_status),
            ),
            links=MerchantLinks(
                operations_history=(
                    reverse("admin:payment_transactionmanager_changelist")
                    + f"?wallet__wallet__merchant__id__exact={merchant.id}"
                ),
                audit_trail=reverse("admin:payment_merchant_change", args=[merchant.id]),
                create_limit=reverse("admin:limits_merchantlimit_add"),
                reports=reverse("admin:payment_transactionmanager_changelist")
                + f"?wallet__wallet__merchant__id__exact={merchant.id}",
            ),
            last_status_change_at=merchant.updated_at,
            last_transaction_at=last_transaction.created_at if last_transaction else None,
        ),
        balances=MerchantBalances(
            currencies=currency_items,
            data_status="READY",
        ),
        wallets=wallet_items,
        limits=limit_items,
        client_lists=list_entries,
        balance_reports=BalanceReports(
            actions=BalanceReportAction(request_report="not_implemented_q1"),
            items=[],
        ),
        transfers=Transfers(actions=TransferActions(create_request=None), requests=[]),
    )
