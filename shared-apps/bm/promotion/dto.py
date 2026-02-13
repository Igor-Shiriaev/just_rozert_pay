from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from bm.promotion.constants import RewardType

from .entities import PromoCode


class CampaignDetail(BaseModel):
    id: int
    title: str
    is_welcome: bool
    is_weekly_cashaback: bool
    high_priority: bool
    active_from: int
    active_to: int
    widget_type: str
    current_iteration_start: Optional[int]
    current_iteration_allowed_period_end: Optional[int]
    next_iteration_start: Optional[int]
    next_iteration_allowed_period_end: Optional[int]
    campaign_type_as_participation_limit: Optional[str]
    preset: dict


class BaseRewardDetails(BaseModel):
    reward_type: Optional[RewardType] = None


class FreebetRewardDetails(BaseRewardDetails):
    reward_type: Optional[RewardType] = RewardType.FREEBET
    amount: Decimal
    currency: str
    freebet_match_type: Optional[str]
    matches_allowed: list[str]
    sport_ids_allowed: list[str]
    freebet_min_odds: Optional[Decimal]
    freebet_max_odds: Optional[Decimal]


class FreespinRewardDetails(BaseRewardDetails):
    reward_type: Optional[RewardType] = RewardType.FREESPIN
    system: str
    game_id: Optional[int]  # NOTE: it's optional for backward compatibility
    game_name: str
    game_uuid: str
    quantity: int


class WagerRewardDetails(BaseRewardDetails):
    reward_type: Optional[RewardType] = RewardType.PROMO_MONEY
    amount: Decimal
    currency: str


class Participant(BaseModel):
    created_at: int
    accepted: bool
    active_duration_days: Optional[float]


class CampaignUserStatus(BaseModel):
    active_participant: Optional[Participant]
    can_participate: bool
    can_accept: bool


class UserPromoCodeResponse(BaseModel):
    activated_promocode: Optional[PromoCode]
    can_participate: bool
