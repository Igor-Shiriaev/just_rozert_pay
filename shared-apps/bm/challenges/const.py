from enum import auto

from bm.common.entities import StrEnum


class ChallengeType(StrEnum):
    OTP = auto()
    TOTP = auto()
    CRYPTO_ADDRESS = auto()
    SKID = auto()  # provider for SmartID + MobileID flows
    RSA_SIGNATURE = auto()
    MAGIC_LINK = auto()


class ChallengeAction(StrEnum):
    PAYMENT_WITHDRAW = auto()

    TOTP_DEVICE_CONFIRMATION = auto()
    TOTP_DEVICE_DEACTIVATION = auto()

    CRYPTO_ADDRESS_CONFIRMATION = auto()
    CONTACT_CONFIRMATION = auto()

    AUTH_REGISTRATION_CONFIRMATION = auto()
    AUTH_SIGNIN = auto()

    PASSWORD_RESET = auto()

    MAGIC_LINK_SIGNIN = auto()
