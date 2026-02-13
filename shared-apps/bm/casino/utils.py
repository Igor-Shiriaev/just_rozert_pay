from currency.const import (
    XBT_PN6, mBTC, IRT, USD, BCH, BCH_PN4, BNB, BNB_PN2, DOGE, DOGE_PP1, BNB_BSC,
    ETH, ETH_PN4, LTC, LTC_PN3, TRX, TRX_PP1, USDT, XRP, XRP_PN1, BSC_PN2, PAXG, PAXG_PN4
)

DEFAULT_CURRENCY_CONVERTION_MAP = {
    XBT_PN6: mBTC,
    BCH_PN4: BCH,
    BNB_PN2: BNB,
    DOGE_PP1: DOGE,
    ETH_PN4: ETH,
    LTC_PN3: LTC,
    TRX_PP1: TRX,
    USDT: USDT,
    XRP_PN1: XRP,
    BSC_PN2: BNB_BSC,
    PAXG_PN4: PAXG,
    IRT: USD,
}


def convert_currency_by_map(
    currency: str,
    currency_convertion_map: dict[str, str]
) -> str:
    return {
        **DEFAULT_CURRENCY_CONVERTION_MAP,
        **currency_convertion_map
    }.get(currency, currency)
