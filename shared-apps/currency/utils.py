import logging
from decimal import Decimal
from typing import List, Optional

from bm import better_lru
from bm.utils import round_decimal
from django.conf import settings

from .const import (
    CURRENCIES,
    CURRENCIES_NOT_CRYPTO,
    CURRENCY_MINOR_UNIT_MULTIPLIERS,
    UNSUPPORTED_INTERNAL_CRYPTO_CURRENCIES
)
from .helpers import CURRENCY_MULTIPLIERS, get_currency_decimal_places
from .models import Rate

logger = logging.getLogger(__name__)


@better_lru.lru_cache(ttl_seconds=60, ignore_in_unittests=True)     # type: ignore[misc]
def get_rates() -> Rate:
    return Rate.objects.order_by('-pk').first()  # type: ignore


def convert_or_scale(
    amount: Decimal,
    currency_from: str,
    currency_to: str,
    places: Optional[int] = -1,
    rates: Optional[Rate] = None
) -> Decimal:
    """If places == -1, get_currency_decimal_places defines the 'places' value."""

    if places == -1:
        places = get_currency_decimal_places(currency_to)
    if currency_from != currency_to:
        # Scaling of related crypto pairs without conversion via USD but
        # by single multiplication or division.
        if any(filter(lambda k: currency_from in k and currency_to in k,    # type: ignore
                      CURRENCY_MULTIPLIERS)):
            amount = Rate.scale_crypto(
                amount=amount, currency_from=currency_from,
                currency_to=currency_to, places=places
            )
        else:
            # regular currency conversion via USD
            rates = rates or get_rates()
            amount = rates.convert(
                amount=amount, currency_from=currency_from,
                currency_to=currency_to, places=places
            )
    else:
        amount = round_decimal(amount, places)

    return amount


def to_minor_units(amount: Decimal, currency: str) -> Decimal:
    return amount * CURRENCY_MINOR_UNIT_MULTIPLIERS[currency]


def from_minor_units(amount: Decimal, currency: str) -> Decimal:
    return amount / CURRENCY_MINOR_UNIT_MULTIPLIERS[currency]


def get_available_currencies(include_unsupported: bool = False) -> List[str]:
    currencies_to_exclude = UNSUPPORTED_INTERNAL_CRYPTO_CURRENCIES
    if include_unsupported:
        currencies_to_exclude = []

    try:
        env_configurations = settings.CURRENT_ENV_CONFIGURATION_FACTORY()  # type: ignore
    except ImportError:
        return [c for c in CURRENCIES if c not in currencies_to_exclude]
    use_crypto = env_configurations.features_availability.coinmarketcap_rates_update
    currencies = CURRENCIES if use_crypto else CURRENCIES_NOT_CRYPTO
    return [c for c in currencies if c not in currencies_to_exclude]
