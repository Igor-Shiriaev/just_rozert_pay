from enum import auto

from bm.common.entities import StrEnum


class SDType(StrEnum):
    EMAIL = auto()
    PHONE = auto()
    ADDRESS = auto()  # street, building, apartment, postcode. country/city could be public
    IDENTITY_SET = auto()  # name, sex, date of birth
    IDENTITY_DOCUMENT = auto()  # ID document number
    BANK_CARD = auto()  # full bank card number, no cvv
    TOTP_SECRET = auto()
    PAYMENT_SYSTEM_CREDENTIALS = auto()
    DEFAULT = auto()


class SDAction(StrEnum):
    ENCRYPT = auto()
    ENCRYPT_WITH_UPDATE = auto()
    DECRYPT = auto()
    DETERMINISTIC_HASH = auto()
