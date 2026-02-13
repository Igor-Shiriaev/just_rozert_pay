from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, validator

from bm.bi.constants import CashflowPeriod
from bm.constants import InstanceId, UserLevel, ProductGroup
from bm.serializers import serialize_decimal


class BaseBIData(BaseModel):

    class Config:
        frozen = True
        json_encoders = {
            Decimal: lambda v: serialize_decimal(v),
        }


class BaseSingleObject(BaseBIData):

    class Config:
        alias_generator = lambda v: v.upper()
        allow_population_by_field_name = True


class TuesdayFreespinData(BaseBIData):
    instance_id: InstanceId
    issued_freespins_amount: int
    qualifying_casino_turnover: Decimal
    qualifying_sport_turnover: Decimal
    qualifying_turnover_currency: str
    reportingdate: date
    user_uuid: UUID
    user_level: UserLevel
    user_currency: str
    brand: str
    domain_group: str
    market: str
    product_group: Optional[ProductGroup]
    language: str

    class Config:
        alias_generator = lambda v: v.upper()
        allow_population_by_field_name = True

    @validator('user_level', pre=True)
    def prepare_user_level(cls, v: str) -> UserLevel:
        return UserLevel(v.lower())


class TuesdayFreespinDataList(BaseBIData):
    items: list[TuesdayFreespinData]


class TuesdayBingoTicketsData(BaseBIData):
    instance_id: InstanceId
    issued_tickets_amount: int
    qualifying_bingo_turnover: Decimal
    qualifying_turnover_currency: str
    reportingdate: date
    user_uuid: UUID
    user_level: UserLevel
    user_currency: str
    brand: str
    domain_group: str
    market: str
    product_group: Optional[ProductGroup]
    language: str

    class Config:
        alias_generator = lambda v: v.upper()
        allow_population_by_field_name = True

    @validator('user_level', pre=True)
    def prepare_user_level(cls, v: str) -> UserLevel:
        return UserLevel(v.lower())


class TuesdayBingoTicketsDataList(BaseBIData):
    items: list[TuesdayBingoTicketsData]


class TuesdaySportFreebetData(BaseBIData):
    instance_id: InstanceId
    issued_freebet_amount: Decimal
    qualifying_sport_turnover: Decimal
    qualifying_turnover_currency: str
    reportingdate: date
    user_uuid: UUID
    user_level: UserLevel
    user_currency: str
    brand: str
    domain_group: str
    market: str
    product_group: Optional[ProductGroup]
    language: str

    class Config:
        alias_generator = lambda v: v.upper()
        allow_population_by_field_name = True

    @validator('user_level', pre=True)
    def prepare_user_level(cls, v: str) -> UserLevel:
        return UserLevel(v.lower())


class TuesdaySportFreebetDataList(BaseBIData):
    items: list[TuesdaySportFreebetData]


class UserCashflowData(BaseBIData):
    total_deposits: Decimal
    total_withdrawals: Decimal
    cashflow: Decimal
    total_bonuses_spent: Decimal
    instance_id: InstanceId
    period: CashflowPeriod
    user_uuid: UUID
    user_currency: str
    brand: str
    domain_group: str
    market: str
    product_group: Optional[ProductGroup]
    language: str
    updated_at: datetime

    class Config:
        alias_generator = lambda v: v.upper()
        allow_population_by_field_name = True


class MondayCashbackData(BaseBIData):
    instance_id: InstanceId
    cashback: Decimal
    cashflow: Decimal
    ngr: Decimal
    issued_cashback_amount: Decimal
    cashback_percentage: Decimal
    deposits_sum: Decimal
    withdrawals_sum: Decimal
    reportingweek: date
    user_id: int
    user_uuid: UUID
    user_level: UserLevel
    user_currency: str
    brand: str
    domain_group: str
    market: str
    product_group: Optional[ProductGroup]
    language: str
    license: str

    class Config:
        alias_generator = lambda v: v.upper()
        allow_population_by_field_name = True

    @validator('user_level', pre=True)
    def prepare_user_level(cls, v: str) -> UserLevel:
        return UserLevel(v.lower())


class MondayCashbackDataList(BaseBIData):
    items: list[MondayCashbackData]


class UserLevelAndProductGroupData(BaseSingleObject):
    instance_id: InstanceId
    user_id: int
    user_uuid: UUID
    user_level: UserLevel
    user_level_historical_max: UserLevel | None
    product_group: ProductGroup | None

    @validator('user_level', pre=True)
    def prepare_user_level(cls, v: str) -> UserLevel:
        return UserLevel(v.lower())

    @validator('user_level_historical_max', pre=True)
    def prepare_user_level_historical_max(cls, v: str | None) -> UserLevel | None:
        if v is None:
            return None
        return UserLevel(v.lower())


class MAReportData(BaseSingleObject):
    report_date: date
    brand: str


class MAUserReport(BaseSingleObject):
    reportingdate: date
    uuid: UUID
    NGR_EUR: Decimal
    Admin_fee_EUR: Decimal
    Turnover_EUR: Decimal
    GGR_EUR: Decimal
    Turnover_Casino_EUR: Decimal
    GGR_Casino_EUR: Decimal
    Turnover_Sport_EUR: Decimal
    GGR_Sport_EUR: Decimal
    Turnover_Virtual_EUR: Decimal
    GGR_Virtual_EUR: Decimal
    Bonus_EUR: Decimal
    Deposit_EUR: Decimal
    Withdrawal_EUR: Decimal
    First_deposit_EUR: Decimal


class MAUserCPAStatus(BaseSingleObject):
    reportingdate: date
    uuid: UUID
    Eligible_For_CPA: int


class MultiaccountData(BaseSingleObject):
    user_id: int
    cluster_id: Optional[int]
    updated_at: datetime

    @validator('cluster_id', pre=True)
    def check_cluster_id(cls, v: int) -> Optional[int]:
        # cluster_id = 0 means that user is not in any cluster.
        if v == 0:
            return None

        return v


class ClusterData(BaseSingleObject):
    cluster_id: Optional[int]
    participants_number: int

    @validator('cluster_id', pre=True)
    def check_cluster_id(cls, v: int) -> Optional[int]:
        # cluster_id = 0 means that user is not in any cluster.
        if v == 0:
            return None

        return v
