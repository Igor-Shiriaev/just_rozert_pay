from enum import StrEnum

from django.db import models
from django.utils.translation import gettext_lazy as _
from rozert_pay.common.const import TransactionType as TT


class ListType(models.TextChoices):
    """The type of the risk list the entry belongs to."""

    WHITE = "WHITE", _("White List")
    GRAY = "GRAY", _("Gray List")
    BLACK = "BLACK", _("Black List")
    MERCHANT_BLACK = "MERCHANT_BLACK", _("Merchant Black List")


class Scope(models.TextChoices):
    """The scope of the entry."""

    WALLET = "WALLET", _("Wallet")
    MERCHANT = "MERCHANT", _("Merchant")
    GLOBAL = "GLOBAL", _("Global")


class OperationType(models.TextChoices):
    ALL = "all", _("All")
    DEPOSIT = TT.DEPOSIT.value, _("Deposit")
    WITHDRAWAL = TT.WITHDRAWAL.value, _("Withdrawal")


class ValidFor(models.TextChoices):
    """The duration for which the entry is valid."""

    H24 = "24H", _("24 hours")
    H168 = "168H", _("7 days")
    H720 = "720H", _("30 days")
    PERMANENT = "PERMANENT", _("Permanent")


class MatchFieldKey(StrEnum):
    CUSTOMER_NAME = "customer_name"
    CUSTOMER_WALLET_ID = "customer_wallet_id"
    MASKED_PAN = "masked_pan"
    EMAIL = "email"
    PHONE = "phone"
    IP = "ip"
    PROVIDER_CODE = "provider_code"


ALLOWED_MATCH_FIELDS: tuple[MatchFieldKey, ...] = tuple(MatchFieldKey)


class Reason(models.TextChoices):
    CHARGEBACK = "CHARGEBACK", _("Chargeback")

