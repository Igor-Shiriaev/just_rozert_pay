from enum import auto
from bm.constants import StrEnum


class VerificationType(StrEnum):
    BASIC_KYC = auto()
    BASIC_AML = auto()
    SOW = auto()
    CARDS_POP = auto()
    POP = auto()
    BASIC_VERIFICATION = auto()


class VerificationInitiator(StrEnum):
    USER = auto()
    SYSTEM = auto()


class UserVerificationStatus(StrEnum):
    INITIAL = auto()
    IN_PROGRESS = auto()
    DOCUMENTS_ACQUIRED = auto()
    SUCCESSFUL = auto()
    FAILED = auto()

    @classmethod
    def get_final_statuses(cls) -> set['UserVerificationStatus']:
        return {
            cls.SUCCESSFUL,
            cls.FAILED,
        }

    @classmethod
    def get_pending_statuses(cls) -> set['UserVerificationStatus']:
        return {
            cls.INITIAL,
            cls.IN_PROGRESS,
            cls.DOCUMENTS_ACQUIRED,
        }
