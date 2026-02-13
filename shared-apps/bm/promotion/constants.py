from enum import auto
from bm.common.entities import StrEnum


class RewardType(StrEnum):
    FREEBET = auto()
    FREESPIN = auto()
    CASINO_FREEBET = auto()
    CASHBACK = auto()
    PROMO_MONEY = auto()
    CAMPAIGN = auto()
    PROMO_TO_REAL_MONEY = auto()


class TargetAudienceType(StrEnum):
    DEAD = 'dead'
    ACTIVE = 'active'
    LEADS = 'leads'
    DEAD_NO_DEPOSITS = 'dead_no_deposits_bonus'
    ACTIVE_NO_DEPOSITS = 'active_no_deposits_bonus'
    LEADS_NO_DEPOSITS = 'leads_no_deposits_bonus'

    def __str__(self) -> str:
        return self.value


class CampaignWidgetType(StrEnum):
    HIDDEN = auto()
    SIMPLE_WAGER = auto()
    SIMPLE_PROMO_WAGER = auto()
    PROMO_WAGER_AFTER_FREEBET = auto()
    PROMO_WAGER_AFTER_FREESPIN = auto()
    PROMO_WAGER_ON_LOSSES = auto()
    PROMO_WAGER_ON_DEPOSIT_PLUS_FREESPIN = auto()
    PROMO_WAGER_ON_SPORT_LOSE = auto()
    PROMO_WAGER_ON_FREEBET_ON_SPORT_LOSE = auto()
    PROMO_WAGER_ON_DEPOSIT_GET_FREESPIN_WITH_PROMO_WAGER = auto()
    PROMO_WAGER_ON_DEPOSIT_GET_FREEBET_WITH_PROMO_WAGER = auto()
    PROMO_WAGER_ON_FREEBET_ON_SPORT_BET = auto()


class CampaignPresetType(StrEnum):
    UNKNOWN = auto()  # for backward compatibility where CampaignPresetType is not known but has to be filled
    DUMMY = auto()
    DUMMY_SPORT_BET = auto()
    CASHBACK = auto()
    FREEBET = auto()
    CASINO_FREEBET = auto()
    FREESPIN = auto()
    PROMO_WAGER = auto()
    PROMO_WAGER_ON_BET = auto()
    PROMO_WAGER_ON_DEPOSIT = auto()
    PROMO_WAGER_ON_DEPOSIT_PLUS_FREESPIN = auto()
    PROMO_WAGER_ON_DEPOSIT_PARAMETRIZED = auto()
    PROMO_WAGER_ON_FREEBET = auto()
    PROMO_WAGER_ON_FREESPIN = auto()
    PROMO_WAGER_ON_CASINO_FREEBET = auto()
    PROMO_WAGER_ON_LOSSES = auto()
    PROMO_WAGER_ON_SPORT_LOSE = auto()  # insurance with wager
    PROMO_WAGER_ON_FREEBET_ON_SPORT_LOSE = auto()  # insurance with freebet with wager
    PROMO_WAGER_ON_FREEBET_ON_SPORT_BET = auto()
    PROMO_WAGER_ON_DEPOSIT_GET_FREESPIN_WITH_PROMO_WAGER = auto()
    PROMO_WAGER_ON_DEPOSIT_GET_FREEBET_WITH_PROMO_WAGER = auto()
    WAGER_ON_FREESPIN = auto()
    WAGER_GET_FREEBET = auto()
    WAGER_GET_FREESPIN = auto()
    WAGER_GET_NEXT_CAMPAIGN = auto()
    WAGER_ON_DEPOSIT_GET_FREEBET = auto()
    WAGER_ON_DEPOSIT_GET_FREESPIN = auto()
    WAGER_ON_DEPOSIT_GET_CASHBACK = auto()
    WAGER_ON_DEPOSIT_GET_FREEBET_WITH_PROMO_WAGER = auto()
    WAGER_ON_SPORT_LOSE = auto()  # insurance
    FREEBET_ON_SPORT_LOSE = auto()  # insurance with freebet
    FREEBET_ON_SPORT_BET = auto()
    FREEBET_ON_DEPOSIT_ON_SPORT_LOSE = auto()

    def __str__(self) -> str:
        return self.name

    @property
    def camelcase(self) -> str:
        return self.name.lower().replace('_', ' ').title().replace(' ', '')


CASINO_STAGE_REWARD_TYPES = [
    RewardType.FREESPIN,
    RewardType.CASINO_FREEBET
]


class WelcomePromoType(StrEnum):
    sports = auto()
    casino = auto()
    no_bonus = auto()
