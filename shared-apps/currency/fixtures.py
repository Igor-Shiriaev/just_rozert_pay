import pytest

from django.utils import timezone

from currency.models import Rate
from currency.const import (
    BTC, mBTC, uBTC, LTC, DOGE, ETH, XRP, RUB, USD, EUR, UAH, KZT,
    KES, CNY, MYR, MZN, BRL, TRY, AUD, NZD, UZS, XBT_PN6, BCH_PN4, ETH_PN4,
    LTC_PN3, NEO_PN2, XRP_PN1, SOL_PN3, TON_PN2,
    DOGE_PP1, ADA, TRX, USDT, JPY, MXN, CAD, KRW, INR, GBP, NOK,
    PLN, CHF, SEK, NGN, UGX, GHS, ZAR, CLP, ARS, COP, PEN, CRC, FWD_PN1
)


@pytest.fixture
@pytest.mark.django_db
def rates() -> Rate:            # type: ignore
    return get_or_create_rates()


def get_or_create_rates() -> Rate:
    try:
        return Rate.objects.get()
    except Rate.DoesNotExist:
        return Rate.objects.create(
            data={
                USD: '1',
                RUB: '60',
                EUR: '0.89',
                KZT: '326.915673',
                UAH: '26.981167',
                CNY: '6.295842',
                MYR: '3.9568',
                KES: '101.11',
                MZN: '62.00',
                BRL: '3.716706',
                TRY: '4.61',
                AUD: '1.421214',
                NZD: '1.510063',
                UZS: '9395',
                BTC: '0.000095973895',
                mBTC: '0.095973895',
                uBTC: '95.973895',
                XBT_PN6: '95.973895',
                BCH_PN4: '32.027672',
                ETH: '0.0052554131',
                ETH_PN4: '52.554131',
                LTC: '0.013566680',
                LTC_PN3: '13.566680',
                'NEO': '0.10235415',
                NEO_PN2: '10.235415',
                SOL_PN3: '4.25415',
                'ETC': '0.13568521',
                XRP: '3.7037037',
                XRP_PN1: '37.037037',
                DOGE: '366.43459',
                DOGE_PP1: '36.643459',
                JPY: '109.63',
                MXN: '20.77',
                CAD: '1.50',
                ADA: '20',
                TON_PN2: '0.031',
                TRX: '56.280955',
                USDT: '1',
                KRW: '1207.49',
                INR: '76.16',
                GBP: '0.81',
                NOK: '9.54',
                PLN: '3.97',
                CHF: '0.95',
                SEK: '9.41',
                NGN: '386.59',
                UGX: '3674.41',
                GHS: '5.78',
                ZAR: '17.00',
                CLP: '793.10',
                ARS: '73.58',
                COP: '3836.00',
                PEN: '3.58',
                CRC: '579.099448',
                # TODO: fill correct value
                FWD_PN1: '1.123',
            },
            datetime_calculated=timezone.now(),
        )
