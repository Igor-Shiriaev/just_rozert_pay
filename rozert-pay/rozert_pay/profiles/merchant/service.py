from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Max, Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from rozert_pay.limits.models import MerchantLimit
from rozert_pay.payment.models import CurrencyWallet, Merchant, PaymentTransaction
from rozert_pay.risk_lists.const import ListType
from rozert_pay.risk_lists.models import RiskListEntry


def _decimal_to_str(value: Decimal) -> str:
    return f"{value:.2f}"


def _build_limit_threshold(limit: MerchantLimit) -> str:
    candidates: tuple[Decimal | int | None, ...] = (
        limit.total_amount,
        limit.max_amount,
        limit.min_amount,
        limit.max_operations,
        limit.max_ratio,
        limit.max_overall_decline_percent,
        limit.max_withdrawal_decline_percent,
        limit.max_deposit_decline_percent,
    )
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, Decimal):
            return _decimal_to_str(candidate)
        return str(candidate)
    return "0"


def _build_limit_period(limit: MerchantLimit) -> dict[str, str | None]:
    period_mapping: dict[str | None, str] = {
        "24h": "DAY",
        "1h": "DAY",
        "beginning_of_day": "DAY",
        "beginning_of_hour": "ROLLING",
    }
    period_code = period_mapping.get(limit.period, "ROLLING")
    return {
        "type": period_code,
        "window": limit.period,
    }


def _build_balance_rows(
    currency_wallets: QuerySet[CurrencyWallet],
) -> list[dict[str, str]]:
    grouped: dict[str, dict[str, Decimal]] = {}
    for currency_wallet in currency_wallets:
        currency = currency_wallet.currency
        if currency not in grouped:
            grouped[currency] = {
                "available": Decimal("0"),
                "pending": Decimal("0"),
                "frozen": Decimal("0"),
            }

        grouped[currency]["available"] += currency_wallet.available_balance
        grouped[currency]["pending"] += currency_wallet.pending_balance
        grouped[currency]["frozen"] += currency_wallet.frozen_balance

    rows: list[dict[str, str]] = []
    for currency, amounts in sorted(grouped.items()):
        total = amounts["available"] + amounts["pending"] + amounts["frozen"]
        rows.append(
            {
                "currency": currency,
                "available": _decimal_to_str(amounts["available"]),
                "pending": _decimal_to_str(amounts["pending"]),
                "frozen": _decimal_to_str(amounts["frozen"]),
                "total": _decimal_to_str(total),
            }
        )
    return rows


def build_merchant_profile(*, merchant: Merchant) -> dict[str, Any]:
    currency_wallets = CurrencyWallet.objects.select_related("wallet").filter(
        wallet__merchant=merchant
    )
    last_transaction_at = PaymentTransaction.objects.filter(
        wallet__wallet__merchant=merchant
    ).aggregate(last_transaction_at=Max("created_at"))["last_transaction_at"]

    risk_status = "GREY" if merchant.risk_control else "WHITE"
    status_block = {
        "operational": {
            "code": "ACTIVE",
            "reason_code": None,
            "comment": None,
            "set_at": None,
        },
        "risk": {
            "code": risk_status,
            "reason_code": None,
            "comment": None,
            "set_at": None,
        },
        "risk_segment": None,
        "business_category": None,
        "kyc_status": None,
        "mcc": None,
    }

    limits: list[dict[str, Any]] = []
    merchant_limits = MerchantLimit.objects.filter(active=True).filter(
        Q(merchant_id=merchant.id) | Q(wallet__merchant_id=merchant.id)
    )

    for limit in merchant_limits.select_related("merchant", "wallet"):
        threshold = _build_limit_threshold(limit)
        limits.append(
            {
                "limit_id": str(limit.id),
                "type": limit.limit_type,
                "scope": "WALLET" if limit.wallet_id else "MERCHANT",
                "period": _build_limit_period(limit),
                "threshold": threshold,
                "usage": {
                    "used": "0",
                    "remaining": threshold,
                    "utilization_percent": 0.0,
                },
                "action_on_exceed": "BLOCK" if limit.decline_on_exceed else "NOTIFY",
                "status": "ACTIVE" if limit.active else "PAUSED",
                "meta": {
                    "created_at": limit.created_at,
                    "created_by": "system",
                    "comment": limit.description or None,
                },
                "links": {
                    "detail": reverse(
                        "admin:limits_merchantlimit_change", args=[limit.id]
                    ),
                    "edit": reverse(
                        "admin:limits_merchantlimit_change", args=[limit.id]
                    ),
                },
                "inherited_from": (
                    f"merchant:{limit.merchant_id}"
                    if limit.wallet_id and limit.merchant_id
                    else None
                ),
            }
        )

    client_lists: list[dict[str, Any]] = []
    entries = RiskListEntry.objects.select_related("customer").filter(merchant=merchant)
    for entry in entries:
        list_type_map: dict[str, str] = {
            ListType.BLACK: "BLACK",
            ListType.WHITE: "WHITE",
            ListType.GRAY: "GREY",
            ListType.MERCHANT_BLACK: "MERCHANT_BLACK",
        }
        if entry.is_deleted:
            status = "REMOVED"
        elif entry.expires_at and entry.expires_at <= timezone.now():
            status = "EXPIRED"
        else:
            status = "ACTIVE"

        client_lists.append(
            {
                "entry_id": str(entry.id),
                "client_id": str(entry.customer_id or ""),
                "list_type": list_type_map.get(entry.list_type, "GREY"),
                "reason_code": entry.reason or "N/A",
                "source": "MANUAL" if entry.added_by_id else "AUTO_RULE",
                "added_at": entry.created_at,
                "status": status,
                "comment": entry.reason or None,
                "expires_at": entry.expires_at,
                "links": None,
            }
        )

    wallet_rows: list[dict[str, Any]] = []
    for currency_wallet in currency_wallets:
        wallet_rows.append(
            {
                "wallet_id": str(currency_wallet.wallet.uuid),
                "currency": currency_wallet.currency,
                "balances": {
                    "available": _decimal_to_str(currency_wallet.available_balance),
                    "pending": _decimal_to_str(currency_wallet.pending_balance),
                    "locked": _decimal_to_str(currency_wallet.frozen_balance),
                },
                "status": "ACTIVE",
                "links": {
                    "wallet_card": reverse(
                        "admin:payment_wallet_change", args=[currency_wallet.wallet_id]
                    ),
                    "wallet_operations": reverse("backoffice-transaction-list")
                    + f"?wallet={currency_wallet.id}",
                },
                "related": {
                    "terminal_id": None,
                    "payment_method": currency_wallet.wallet.system.name,
                },
            }
        )

    return {
        "merchant": {
            "id": str(merchant.id),
            "display_name": merchant.name,
            "legal_name": None,
            "created_at": merchant.created_at,
            "status": status_block,
            "last_status_change_at": None,
            "last_transaction_at": last_transaction_at,
            "links": {
                "operations_history": reverse("backoffice-transaction-list")
                + f"?merchant_id={merchant.id}",
                "audit_trail": reverse("admin:auditlog_logentry_changelist")
                + f"?content_type__model=merchant&object_id={merchant.id}",
                "create_limit": reverse("admin:limits_merchantlimit_add")
                + f"?merchant={merchant.id}",
                "create_wallet_transfer": None,
                "reports": None,
            },
        },
        "balances": {
            "currencies": _build_balance_rows(currency_wallets),
            "data_status": "READY",
        },
        "wallets": wallet_rows,
        "limits": limits,
        "client_lists": client_lists,
        "balance_reports": {
            "actions": {
                "request_report": "",
            },
            "items": [],
        },
        "transfers": {
            "actions": {
                "create_request": None,
            },
            "requests": [],
        },
    }
