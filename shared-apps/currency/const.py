import sys

from openapi.common import DataValues, get_openapi_yaml_data_values

OPENAPI_DATA_VALUES: DataValues = get_openapi_yaml_data_values()


def load_core_currencies_from_openapi_data_values() -> None:
    thismodule = sys.modules[__name__]

    crypto_currencies: list[str] = list()
    currency_minor_unit_multipliers: dict[str, int] = dict()

    for currency_config in OPENAPI_DATA_VALUES['currencies']:
        currency_name = currency_config['name']  # no `upper()` because of `mBTC`.
        if currency_name == 'BNB-BSC':
            setattr(thismodule, 'BNB_BSC', currency_name)
        else:
            setattr(thismodule, currency_name, currency_name)

        is_natively_supported = currency_config['is_natively_supported']
        if is_natively_supported and currency_config['crypto']:
            crypto_currencies.append(currency_name)

        if currency_config['minor_unit_multiplier'] is not None:
            currency_minor_unit_multipliers[currency_name] = currency_config['minor_unit_multiplier']

    setattr(thismodule, 'CRYPTO_CURRENCIES', crypto_currencies)

    setattr(thismodule, 'CURRENCY_MINOR_UNIT_MULTIPLIERS', currency_minor_unit_multipliers)

# fiat currencies
USD = ''
EUR = ''
RUB = ''
MYR = ''
CNY = ''
KES = ''
UAH = ''
KZT = ''
MZN = ''
BRL = ''
TRY = ''
AUD = ''
NZD = ''
UZS = ''
JPY = ''
MXN = ''
CAD = ''
KRW = ''
INR = ''
GBP = ''
NOK = ''
PLN = ''
CHF = ''
SEK = ''
NGN = ''
UGX = ''
GHS = ''
ZAR = ''
CLP = ''
ARS = ''
COP = ''
PEN = ''
IRT = ''
DKK = ''
THB = ''
VND = ''
IDR = ''
PHP = ''
CRC = ''
RSD = ''

XBT_PN6 = ''  # 1 BTC * 10^-6
BCH_PN4 = ''  # 1 BCH * 10^-4
ETH_PN4 = ''  # 1 ETH * 10^-4
LTC_PN3 = ''  # 1 LTC * 10^-3
NEO_PN2 = ''  # 1 NEO * 10^-2
XRP_PN1 = ''  # 1 XRP * 10^-1
DOGE_PP1 = ''  # 1 DOGE * 10^1
BNB_PN2 = ''  # 1 BNB * 10^-2
TRX_PP1 = ''  # 1 TRX * 10^1
SOL_PN3 = ''  # 1 SOL * 10^-3
TON_PN2 = ''  # 1 TON * 10^-2
ADA = ''
TON = ''
SOL = ''
TRX = ''
USDT = ''
USDTE = ''
USDTT = ''
USDTB = ''
USDC = ''
USDCS = ''
USDTTON = ''
BUSD = ''
BSC_PN2 = ''
PAXG_PN4 = ''

FWD = ''
FWD_PN1 = ''    # 1 rewind token FWD * 10^4

# scaled
mBTC = ''
uBTC = ''
mLTC = ''
mETH = ''
# raw
BTC = ''
LTC = ''
DOGE = ''
ETH = ''
XRP = ''
BCH = ''
NEO = ''
SOL = ''
BNB = ''
BNB_BSC = ''
DAI = ''
PAXG = ''
BRZ = ''


# TODO: refactoring of currencies categories
CRYPTO_CURRENCIES: list[str] = []

# See https://en.wikipedia.org/wiki/ISO_4217 for details
CURRENCY_MINOR_UNIT_MULTIPLIERS: dict[str, int] = {}

load_core_currencies_from_openapi_data_values()

EXTERNAL_CRYPTO_NAME_TO_INTERNAL_CRYPTO_NAME_MAP = {
    ADA: ADA,
    TON: TON_PN2,
    SOL: SOL_PN3,
    USDT: USDT,
    USDTE: USDTE,
    USDTT: USDTT,
    USDTB: USDTB,
    BTC: XBT_PN6,
    LTC: LTC_PN3,
    DOGE: DOGE_PP1,
    ETH: ETH_PN4,
    XRP: XRP_PN1,
    BCH: BCH_PN4,
    NEO: NEO_PN2,
    BNB: BNB_PN2,
    TRX: TRX_PP1,
    USDC: USDC,
    USDCS: USDCS,
    USDTTON: USDTTON,
    BUSD: BUSD,
    BNB_BSC: BSC_PN2,
    DAI: DAI,
    BRZ: BRZ,
    PAXG: PAXG_PN4,
    FWD: FWD_PN1,
}

INTERNAL_CRYPTO_NAME_MAP_TO_EXTERNAL_CRYPTO_NAME = {
    v: k for k, v in EXTERNAL_CRYPTO_NAME_TO_INTERNAL_CRYPTO_NAME_MAP.items()
}

# These currencies rate is around 1 USD so it's enough
# to use 2 decimal places in conversion operations.
CURRENCIES_EXCLUDED_FROM_DECIMAL_PLACES_CHECK = [
    ADA, USDT, USDTE, USDTT, USDTB, USDC, USDCS, USDTTON, BUSD, DAI, BRZ,
]

# used to extend currencies choices in Currency of common/fields.py
FOREIGN_CURRENCIES = [
    BTC, mBTC, uBTC, LTC, mLTC, DOGE, ETH, mETH, XRP, BCH, NEO, BNB,
    ADA, USDT, USDTE, USDTT, USDTB, TRX, USDC, USDCS, USDTTON, BUSD, BNB_BSC, DAI, BRZ, PAXG,
    FWD, SOL, TON
]

CRYPTO_FOREIGN_CURRENCIES = FOREIGN_CURRENCIES

INTERNAL_CURRENCIES = [
    v for v in EXTERNAL_CRYPTO_NAME_TO_INTERNAL_CRYPTO_NAME_MAP.values()
    if v not in EXTERNAL_CRYPTO_NAME_TO_INTERNAL_CRYPTO_NAME_MAP
]

CURRENCIES = [
    USD, EUR, RUB, UAH, KZT, KES, MZN, BRL, TRY, AUD, NZD, UZS,
    XBT_PN6, BCH_PN4, ETH_PN4, LTC_PN3, NEO_PN2, XRP_PN1, DOGE_PP1,
    ADA, USDT, JPY, MXN, CAD, BNB_PN2, KRW, CNY, INR, GBP, NOK, PLN,
    CHF, SEK, NGN, UGX, GHS, ZAR, CLP, ARS, COP, PEN, USDTE, USDTT,
    USDTB, IRT, TRX_PP1, DKK, THB, VND, IDR, PHP, MYR, CRC, USDC, BUSD,
    BSC_PN2, DAI, BRZ, PAXG_PN4, RSD, FWD_PN1, SOL_PN3, USDCS, USDTTON, TON_PN2,
]

assert all([
    all(EXTERNAL_CRYPTO_NAME_TO_INTERNAL_CRYPTO_NAME_MAP.keys()),
    all(EXTERNAL_CRYPTO_NAME_TO_INTERNAL_CRYPTO_NAME_MAP.values()),
    all([CURRENCIES_EXCLUDED_FROM_DECIMAL_PLACES_CHECK]),
    all([FOREIGN_CURRENCIES]),
    all([CURRENCIES]),
]), 'Some currency did not load.'

CURRENCIES_NOT_CRYPTO = []

# Check CURRENCY_MINOR_UNIT_MULTIPLIERS consistency
for cur in CURRENCIES:
    if cur not in CRYPTO_CURRENCIES and cur not in FOREIGN_CURRENCIES:
        CURRENCIES_NOT_CRYPTO.append(cur)
        assert cur in CURRENCY_MINOR_UNIT_MULTIPLIERS, f'Missed minor unit multiplier for {cur}'


UNSUPPORTED_INTERNAL_CRYPTO_CURRENCIES = [NEO_PN2, BUSD]
