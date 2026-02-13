from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
from uuid import UUID

from bm.constants import BetType, CasinoProviderType, BetProducerType
from bm.datatypes import Money
from bm.promotion.constants import CampaignPresetType
from bm.utils import round_decimal
from pydantic import BaseModel, validator

from .constants import RewardType, TargetAudienceType


def round_reward_amount_validator(amount: Optional[Money]) -> Optional[Money]:
    if amount is None:
        return None
    return Money(
        value=round_decimal(
            value=amount.value,
            places=2,  # billing does not support precision > 2 at the moment.
        ),
        currency=amount.currency,
    )


class PromoCode(BaseModel):
    code: str
    ma_token: Optional[str] = None
    target_audience: Optional[TargetAudienceType] = None


class RewardParams(ABC, BaseModel):
    withdrawals_disabled_until_apply: bool = False
    accept_on_create: bool = False

    @property
    @abstractmethod
    def currency(self) -> Optional[str]:
        """It could be the case that stage reward has nothing to do with
        money, so currency should be None in this case.
        """
        ...


class FreebetRewardParams(RewardParams):
    amount: Money
    sport_ids: Optional[list[str]]
    tournament_ids: Optional[list[str]] = None
    match_ids: Optional[list[str]]
    min_odds: Optional[Decimal]
    bet_type: Optional[BetType]
    max_odds: Optional[Decimal]
    producer_type: Optional[BetProducerType] = None

    quantity: int = 1

    promo_identifier: Optional[str] = None
    do_not_accrue_win_amount: bool = False

    # validator
    _round_amount = validator('amount', allow_reuse=True)(round_reward_amount_validator)  # type: ignore

    @property
    def currency(self) -> Optional[str]:
        return self.amount.currency

class BaseCasinoRewardParams(RewardParams, ABC):
    casino_provider: CasinoProviderType
    game_name: str
    game_uuid: UUID
    game_id: Optional[int] = None  # NOTE: it's optional for backward compatibility
    game_type: Optional[str] = None  # NOTE: it's optional for backward compatibility
    extra: dict

    promo_identifier: Optional[str] = None
    do_not_accrue_win_amount: bool = False


class FreespinRewardParams(BaseCasinoRewardParams):
    game_foreign_system_id: Optional[str] = None
    quantity: int
    # NOTE: user can have multiple currencies, so we need to point to the currency in which user
    # is getting freespins. "None" is treated as a base_currency.
    user_currency: Optional[str] = None
    spin_amount: Optional[Money] = None

    @property
    def currency(self) -> Optional[str]:
        if self.user_currency:
            return self.user_currency
        if self.spin_amount is None:
            return None
        return self.spin_amount.currency


class CasinoFreebetRewardParams(BaseCasinoRewardParams):
    """
    It is bonus that is given as some money amount and only for live casino
    games like blackjack, roulette, etc.
    """
    amount: Money

    # validator
    _round_amount = validator('amount', allow_reuse=True)(round_reward_amount_validator)  # type: ignore

    @property
    def currency(self) -> Optional[str]:
        return self.amount.currency


class CashbackRewardParams(RewardParams):
    amount: Money

    # validator
    _round_amount = validator('amount', allow_reuse=True)(round_reward_amount_validator)  # type: ignore

    @property
    def currency(self) -> Optional[str]:
        return self.amount.currency


class PromoMoneyStageRewardCampaignParams(BaseModel):
    preset_type: CampaignPresetType
    is_wager_on_sport: bool
    is_wager_on_casino: bool
    is_wager_on_casino_live: bool = False  # backward compatibility, added on 2025-10-22
    is_wager_on_bingo: bool = False  # backward compatibility, added on 2025-10-22
    is_welcome_campaign: bool = False  # backward compatibility, added on 2024-04-26
    is_on_deposit_campaign: bool = False  # backward compatibility, added on 2024-04-26


# Just more suitable alias for use in betmaster service (so that we do not
# expose information about stages.
PromoMoneyCampaignParams = PromoMoneyStageRewardCampaignParams


class PromoMoneyRewardParams(RewardParams):
    wallet_account: UUID
    amount: Money
    campaign: PromoMoneyStageRewardCampaignParams

    # validator
    _round_amount = validator('amount', allow_reuse=True)(round_reward_amount_validator)  # type: ignore

    @property
    def currency(self) -> Optional[str]:
        return self.amount.currency


class PromoToRealMoneyRewardParams(RewardParams):
    wallet_account: UUID
    amount_to_transfer: Optional[Money] = None
    max_amount: Optional[Money] = None

    # validator
    _round_max_amount = validator('max_amount', allow_reuse=True)(round_reward_amount_validator)  # type: ignore

    @property
    def currency(self) -> Optional[str]:
        if self.amount_to_transfer is not None:
            return self.amount_to_transfer.currency
        if self.max_amount is None:
            return None
        return self.max_amount.currency


STAGE_REWARD_PARAMS_BY_TYPE = {
    RewardType.FREEBET: FreebetRewardParams,
    RewardType.FREESPIN: FreespinRewardParams,
    RewardType.CASINO_FREEBET: CasinoFreebetRewardParams,
    RewardType.CASHBACK: CashbackRewardParams,
    RewardType.PROMO_MONEY: PromoMoneyRewardParams,
    RewardType.PROMO_TO_REAL_MONEY: PromoToRealMoneyRewardParams,
}


class MarketingOfferData(BaseModel):
    promo_id: str
    is_enabled: bool
    mode: str
    on_site_links: list[str]
