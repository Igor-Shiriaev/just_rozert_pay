import re
from decimal import Decimal
from math import log10

from .const import (    # NOQA
    ADA,
    SOL,
    TON,
    TON_PN2,
    BCH,
    BCH_PN4,
    BNB,
    BNB_BSC,
    BNB_PN2,
    BSC_PN2,
    BTC,
    BUSD,
    CURRENCY_MINOR_UNIT_MULTIPLIERS,
    DAI,
    DOGE,
    DOGE_PP1,
    ETH,
    ETH_PN4,
    EXTERNAL_CRYPTO_NAME_TO_INTERNAL_CRYPTO_NAME_MAP,
    LTC,
    LTC_PN3,
    NEO,
    NEO_PN2,
    SOL_PN3,
    PAXG,
    PAXG_PN4,
    TRX,
    TRX_PP1,
    USDC,
    USDCS,
    USDTTON,
    USDT,
    USDTE,
    USDTT,
    USDTB,
    XBT_PN6,
    XRP,
    XRP_PN1,
    mBTC,
    mETH,
    mLTC,
    uBTC,
    FWD,
    FWD_PN1,
)


def get_internal_blockchain_currency_by_external_blockchain_currency(
    *,
    external_blockchain_currency: str,
) -> str:
    return EXTERNAL_CRYPTO_NAME_TO_INTERNAL_CRYPTO_NAME_MAP[external_blockchain_currency]


def get_correction(*, crypto_currency_name: str) -> Decimal:
    """
    Public method to decode currency rate correction code into decimal value.
    :param crypto_currency_name: Internal crypto currency name with encoded rate
    correction.
    Correction examples:
        XBT_PN6 (XBT Power Negative 6) means XBT * 10^-6
        DOGE_PP1 (DOGE Power Positive 1) means DOGE * 10^1
    :type crypto_currency_name: str
    """

    if crypto_currency_name == mLTC:
        crypto_currency_name = 'LTC_PN3'

    if crypto_currency_name == mETH:
        crypto_currency_name = 'ETH_PN3'

    if crypto_currency_name == mBTC:
        crypto_currency_name = 'XBT_PN3'

    if crypto_currency_name == uBTC:
        crypto_currency_name = 'XBT_PN6'

    data = crypto_currency_name.split('_')
    if len(data) == 1:
        return Decimal('1')

    _, correction_code = data
    parsed = re.match(r'^P(?P<sign>[NP])(?P<value>\d+)', correction_code)
    assert parsed is not None, 'invalid internal crypto currency name'
    sign, value = parsed.groups()
    value_int = int(value)
    if sign == 'N':
        value_int = -value_int
    return Decimal('10') ** value_int


CURRENCY_GROUPS = (
    (BTC, mBTC, uBTC, XBT_PN6),
    (ETH, mETH, ETH_PN4),
    (DOGE, DOGE_PP1),
    (LTC, mLTC, LTC_PN3),
    (XRP, XRP_PN1),
    (BCH, BCH_PN4),
    (NEO, NEO_PN2),
    (BNB, BNB_PN2),
    (SOL, SOL_PN3),
    (TON, TON_PN2),
    (ADA, ),
    (USDT, ),
    (USDTE, ),
    (USDTT, ),
    (USDTB, ),
    (TRX, TRX_PP1),
    (USDC, ),
    (USDCS, ),
    (USDTTON, ),
    (BNB_BSC, BSC_PN2),
    (DAI, ),
    (PAXG, PAXG_PN4),
    (FWD, FWD_PN1),
)


"""
CURRENCY_MULTIPLIERS in result
{
    ('BTC', 'mBTC', 'uBTC', 'XBT_PN6'): {'BTC': Decimal('1'),
                                         'mBTC': Decimal('0.001'),
                                         'uBTC': Decimal('0.000001'),
                                         'XBT_PN6': Decimal('0.000001')},
    ...
}
"""
CURRENCY_MULTIPLIERS = {
    group: {
        currency:
            get_correction(crypto_currency_name=currency) for currency in group
    } for group in CURRENCY_GROUPS
}


def get_currency_decimal_places(currency: str) -> int:
    if mult := CURRENCY_MINOR_UNIT_MULTIPLIERS.get(currency):
        # For mult 100 return 2, 1000 -> 3, etc.
        return int(log10(mult))
    return 2
