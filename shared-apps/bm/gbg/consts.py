from enum import auto

from bm.constants import StrEnum


class GBGVerificationType(StrEnum):
    TWO_PLUS_TWO = auto()
    PEP_AND_SANCTIONS = auto()
    AFFORDABILITY = auto()
    FORCE_OVERRIDE = auto()


class GBGTransactionStatus(StrEnum):
    SUCCESSFUL = auto()
    FAILED = auto()


class GBGApplicantVerificationStatus(StrEnum):
    SUCCESSFUL = auto()
    FAILED = auto()
    PENDING = auto()
    AWAITING_SUMSUB = auto()
