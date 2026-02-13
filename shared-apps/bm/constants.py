from enum import IntEnum, auto

from bm.casino.constants import CasinoProviderType  # NOQA
from bm.common.entities import StrEnum


# NOTE: share with auth module?
class ContactType(StrEnum):
    PHONE = 'phone'
    EMAIL = 'email'
    ACCOUNT_ID = 'account_id'
    ESTONIAN_ID = 'estonian_id'


COMMUNICATION_CHANNEL_CONTACT_TYPES = [ContactType.PHONE, ContactType.EMAIL]


class LoginType(StrEnum):
    PHONE = 'phone'
    EMAIL = 'email'
    ZIMPLER = 'zimpler'
    ACCOUNT_ID = 'account_id'
    ESTONIAN_ID = 'estonian_id'
    WHATSAPP = 'whatsapp'


class CasinoActionType(StrEnum):
    ROLLBACK_BET = auto()
    ROLLBACK_WIN = auto()
    BET = auto()
    WIN = auto()


class CasinoActionStatus(StrEnum):
    SUCCESS = auto()
    ROLLBACK = auto()
    FAILED = auto()


class SportActionState(StrEnum):
    ACCEPTED = auto()
    WIN = auto()
    VOIDED_WIN = auto()
    DEAD_HEATED_HALF_WIN = auto()
    LOSE = auto()
    VOIDED_LOSE = auto()
    REFUNDED_LOSE = auto()
    PUSHED = auto()
    CANCELED = auto()
    CASHED_OUT = auto()


class BetType(StrEnum):
    EXPRESS = auto()
    SINGLE = auto()


class BetProducerType(StrEnum):
    LIVE = auto()
    PREMATCH = auto()


class ChargeMethod(StrEnum):
    CASH = auto()  # NOTE: wrong naming, means REAL or PROMO money
    PROMO = auto()  # NOTE: wrong naming, means FREEBET or FREESPIN


class ProductGroup(StrEnum):
    ### Deprecated values, kept for backward compatibility
    CASINO = 'CASINO'
    VIRTUAL_SPORT = 'VIRTUAL_SPORT'
    ###

    SPORT = 'SPORT'
    ESPORT = 'ESPORT'
    RACING = 'RACING'
    BINGO = 'BINGO'
    INSTANT = 'INSTANT'
    LIVE = 'LIVE'
    TABLE = 'TABLE'
    SLOT = 'SLOT'
    VIRTUAL = 'VIRTUAL'
    MIX = 'MIX'
    UNDEFINED = 'UNDEFINED'


class VirtualSportProviderType(StrEnum):
    BETBY = auto()
    GOLDEN_RACE = auto()


class RacingProviderType(StrEnum):
    PYTHIA = auto()


class VirtualSportBetStatus(StrEnum):
    NEW = auto()
    WIN = auto()
    LOSE = auto()
    CANCELED = auto()
    OTHER = auto()


class ActionCreator(StrEnum):
    USER = auto()
    ADMIN = auto()
    SYSTEM = auto()


# Used in obsolete events BET_RESOLVED and GGR_CHANGED.
class ActionSource(StrEnum):
    SPORT = auto()
    CASINO = auto()
    VIRTUAL_SPORT = auto()


class UserLevel(StrEnum):
    regular = auto()
    previp = auto()
    vip = auto()


class LoyaltyProgramType(StrEnum):
    cashback = auto()
    rewind = auto()
    custom = auto()


class TTL(IntEnum):
    seconds_3 = 3
    seconds_5 = 5
    minutes_1 = 60
    minutes_5 = 60 * 5
    minutes_15 = 60 * 15
    minutes_30 = 60 * 30
    hours_1 = 60 * 60
    days_1 = 60 * 60 * 24


class InstanceId(IntEnum):
    development = 9
    production = 1
    production_malta = 2
    production_iom = 3
    production_centro = 4


class Product(StrEnum):
    sports = auto()
    casino = auto()
    virtuals = auto()


class Period(StrEnum):
    daily = 'daily'
    weekly = 'weekly'
    monthly = 'monthly'
    arbitrary = 'arbitrary'


class PermissionActionType(StrEnum):
    DEPOSIT = 'deposit'
    WITHDRAWAL = 'withdrawal'
    SPORT_BETTING = 'sport_betting'
    VIRTUAL_SPORT_BETTING = 'virtual_sport_betting'
    CASINO_BETTING = 'casino_betting'
    RACING_BETTING = 'racing_betting'
    BONUS = 'bonus'


LOCAL_MEMORY_CACHE = 'local_memory_cache'
LOW_PRIORITY_CACHE = 'low_priority'
LOCAL_FILE_CACHE = 'file'


class ComplianceMessageType(StrEnum):
    INFO = auto()
