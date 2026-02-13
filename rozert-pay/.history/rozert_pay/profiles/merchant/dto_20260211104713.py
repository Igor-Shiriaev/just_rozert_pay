from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, NotRequired, TypedDict

from pydantic import BaseModel


class MerchantLinks(TypedDict, total=False):
    operations_history: str
    audit_trail: str
    create_limit: str
    create_wallet_transfer: str
    reports: str


class MerchantOperationalStatus(TypedDict, total=False):
    code: Literal["ACTIVE", "INACTIVE", "SUSPENDED", "TERMINATED"]
    reason_code: str
    comment: str
    set_at: datetime


class MerchantRiskStatus(TypedDict, total=False):
    code: Literal["WHITE", "GREY", "BLACK"]
    reason_code: str
    comment: str
    set_at: datetime


class MerchantStatus(TypedDict, total=False):
    operational: MerchantOperationalStatus
    risk: MerchantRiskStatus
    risk_segment: Literal["LOW", "MEDIUM", "HIGH"]
    business_category: str
    kyc_status: Literal["PENDING", "APPROVED", "EXPIRED"]
    mcc: str


class MerchantInfo(TypedDict):
    id: str
    display_name: str
    created_at: datetime
    status: MerchantStatus
    links: MerchantLinks
    legal_name: NotRequired[str]
    last_status_change_at: NotRequired[datetime]
    last_transaction_at: NotRequired[datetime]


class CurrencyBalance(TypedDict):
    currency: str
    available: str
    pending: str
    frozen: str
    total: str


class MerchantBalances(TypedDict):
    currencies: List[CurrencyBalance]
    data_status: Literal["READY", "UNAVAILABLE"]


class WalletRelated(TypedDict, total=False):
    terminal_id: str
    payment_method: str


class WalletLinks(TypedDict):
    wallet_card: str
    wallet_operations: str


class WalletBalances(TypedDict):
    available: str
    pending: str
    locked: str


class WalletInfo(TypedDict):
    wallet_id: str
    currency: str
    balances: WalletBalances
    status: Literal["ACTIVE", "FROZEN", "CLOSED"]
    links: WalletLinks
    related: NotRequired[WalletRelated]


class LimitPeriod(TypedDict, total=False):
    type: Literal["DAY", "WEEK", "MONTH", "ROLLING"]
    window: str


class LimitUsage(TypedDict):
    used: str
    remaining: str
    utilization_percent: float


class LimitMeta(TypedDict):
    created_at: datetime
    created_by: str
    comment: NotRequired[str]


class LimitLinks(TypedDict, total=False):
    detail: str
    edit: str


class LimitInfo(TypedDict):
    limit_id: str
    type: str
    scope: Literal["MERCHANT", "TERMINAL", "WALLET"]
    period: LimitPeriod
    threshold: str
    usage: LimitUsage
    action_on_exceed: Literal["BLOCK", "THROTTLE", "MANUAL_REVIEW", "NOTIFY"]
    status: Literal["ACTIVE", "PAUSED", "EXPIRED"]
    meta: LimitMeta
    links: LimitLinks
    inherited_from: NotRequired[str]


class ClientListLinks(TypedDict, total=False):
    client_card: str


class ClientListEntry(TypedDict):
    entry_id: str
    client_id: str
    list_type: Literal["BLACK", "GREY", "WHITE"]
    reason_code: str
    source: Literal["MANUAL", "AUTO_RULE", "EXTERNAL"]
    added_at: datetime
    status: Literal["ACTIVE", "EXPIRED", "REMOVED"]
    comment: NotRequired[str]
    expires_at: NotRequired[datetime]
    links: NotRequired[ClientListLinks]


class BalanceReportAction(TypedDict):
    request_report: str


class BalanceReportItem(TypedDict):
    report_id: str
    period_from: datetime
    period_to: datetime
    format: Literal["CSV", "XLSX", "PDF"]
    type: Literal["AGGREGATED", "BY_WALLET"]
    status: Literal["QUEUED", "READY", "FAILED"]
    created_at: datetime
    ready_at: NotRequired[datetime]
    download_link: NotRequired[str]


class BalanceReports(TypedDict):
    actions: BalanceReportAction
    items: List[BalanceReportItem]


class TransferLinks(TypedDict, total=False):
    detail: str


class TransferRequest(TypedDict):
    request_id: str
    type: Literal["INTERNAL_TRANSFER", "FX_CONVERSION"]
    source_wallet: str
    destination_wallet: str
    amount: str
    currency: str
    status: Literal[
        "CREATED",
        "PENDING_APPROVAL",
        "APPROVED",
        "EXECUTED",
        "REJECTED",
        "FAILED",
    ]
    created_at: datetime
    fx_rate: NotRequired[str]
    comment: NotRequired[str]
    updated_at: NotRequired[datetime]
    updated_by: NotRequired[str]
    links: NotRequired[TransferLinks]


class TransferActions(TypedDict, total=False):
    create_request: str


class Transfers(TypedDict):
    actions: TransferActions
    requests: List[TransferRequest]


class MerchantProfileDto(BaseModel):
    merchant: MerchantInfo
    balances: MerchantBalances
    wallets: List[WalletInfo]
    limits: List[LimitInfo]
    client_lists: List[ClientListEntry]
    balance_reports: BalanceReports
    transfers: Transfers


__all__ = [
    "BalanceReportAction",
    "BalanceReportItem",
    "BalanceReports",
    "ClientListEntry",
    "ClientListLinks",
    "CurrencyBalance",
    "LimitInfo",
    "LimitLinks",
    "LimitMeta",
    "LimitPeriod",
    "LimitUsage",
    "MerchantBalances",
    "MerchantInfo",
    "MerchantLinks",
    "MerchantOperationalStatus",
    "MerchantProfileDto",
    "MerchantRiskStatus",
    "MerchantStatus",
    "TransferActions",
    "TransferLinks",
    "TransferRequest",
    "Transfers",
    "WalletBalances",
    "WalletInfo",
    "WalletLinks",
    "WalletRelated",
]
