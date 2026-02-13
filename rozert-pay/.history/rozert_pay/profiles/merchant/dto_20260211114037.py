from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from rozert_pay.common import const
from rozert_pay.payment.models import Merchant


class MerchantLinks(BaseModel):
    operations_history: str
    audit_trail: str
    create_limit: Optional[str] = None
    create_wallet_transfer: Optional[str] = None
    reports: Optional[str] = None


class MerchantOperationalStatus(BaseModel):
    code: const.MerchantOperationalStatus
    reason_code: Optional[str] = None
    comment: Optional[str] = None
    set_at: Optional[datetime] = None


class MerchantRiskStatus(BaseModel):
    code: Merchant.RiskStatus
    reason_code: Optional[str] = None
    comment: Optional[str] = None
    set_at: Optional[datetime] = None


class MerchantStatus(BaseModel):
    operational: MerchantOperationalStatus
    risk: MerchantRiskStatus
    risk_segment: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None
    business_category: Optional[str] = None
    kyc_status: Optional[Literal["PENDING", "APPROVED", "EXPIRED"]] = None
    mcc: Optional[str] = None


class MerchantInfo(BaseModel):
    id: str
    display_name: str
    created_at: datetime
    status: MerchantStatus
    links: MerchantLinks
    legal_name: Optional[str] = None
    last_status_change_at: Optional[datetime] = None
    last_transaction_at: Optional[datetime] = None


class CurrencyBalance(BaseModel):
    currency: str
    available: str
    pending: str
    frozen: str
    total: str


class MerchantBalances(BaseModel):
    currencies: List[CurrencyBalance]
    data_status: Literal["READY", "UNAVAILABLE"]


class WalletRelated(BaseModel):
    terminal_id: Optional[str] = None
    payment_method: Optional[str] = None


class WalletLinks(BaseModel):
    wallet_card: str
    wallet_operations: str


class WalletBalances(BaseModel):
    available: str
    pending: str
    locked: str


class WalletInfo(BaseModel):
    wallet_id: str
    currency: str
    balances: WalletBalances
    status: Literal["ACTIVE", "FROZEN", "CLOSED"]
    links: WalletLinks
    related: Optional[WalletRelated] = None


class LimitPeriod(BaseModel):
    type: Literal["DAY", "WEEK", "MONTH", "ROLLING"]
    window: Optional[str] = None


class LimitUsage(BaseModel):
    used: str
    remaining: str
    utilization_percent: float


class LimitMeta(BaseModel):
    created_at: datetime
    created_by: str
    comment: Optional[str] = None


class LimitLinks(BaseModel):
    detail: str
    edit: Optional[str] = None


class LimitInfo(BaseModel):
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
    inherited_from: Optional[str] = None


class ClientListLinks(BaseModel):
    client_card: Optional[str] = None


class ClientListEntry(BaseModel):
    entry_id: str
    client_id: str
    list_type: Literal["BLACK", "GREY", "WHITE"]
    reason_code: str
    source: Literal["MANUAL", "AUTO_RULE", "EXTERNAL"]
    added_at: datetime
    status: Literal["ACTIVE", "EXPIRED", "REMOVED"]
    comment: Optional[str] = None
    expires_at: Optional[datetime] = None
    links: Optional[ClientListLinks] = None


class BalanceReportAction(BaseModel):
    request_report: str


class BalanceReportItem(BaseModel):
    report_id: str
    period_from: datetime
    period_to: datetime
    format: Literal["CSV", "XLSX", "PDF"]
    type: Literal["AGGREGATED", "BY_WALLET"]
    status: Literal["QUEUED", "READY", "FAILED"]
    created_at: datetime
    ready_at: Optional[datetime] = None
    download_link: Optional[str] = None


class BalanceReports(BaseModel):
    actions: BalanceReportAction
    items: List[BalanceReportItem]


class TransferLinks(BaseModel):
    detail: Optional[str] = None


class TransferRequest(BaseModel):
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
    fx_rate: Optional[str] = None
    comment: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    links: Optional[TransferLinks] = None


class TransferActions(BaseModel):
    create_request: Optional[str] = None


class Transfers(BaseModel):
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
