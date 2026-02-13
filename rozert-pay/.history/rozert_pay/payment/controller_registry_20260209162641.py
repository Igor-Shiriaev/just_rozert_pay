from typing import Any, TypedDict

from rozert_pay.common import const
from rozert_pay.payment.systems.appex.appex_controller import appex_controller
from rozert_pay.payment.systems.base_controller import PaymentSystemController
from rozert_pay.payment.systems.bitso_spei.bitso_spei_controller import (
    bitso_spei_controller,
)
from rozert_pay.payment.systems.cardpay_systems.cardpay_applepay.controller import (
    cardpay_applepay_controller,
)
from rozert_pay.payment.systems.cardpay_systems.cardpay_cards.controller import (
    cardpay_cards_controller,
)
from rozert_pay.payment.systems.conekta.conekta_oxxo import conekta_oxxo_controller
from rozert_pay.payment.systems.d24_mercadopago.controller import (
    d24_mercadopago_controller,
)
from rozert_pay.payment.systems.ilixium.ilixium_controller import ilixium_controller
from rozert_pay.payment.systems.mpesa_mz.controller import mpesa_mz_controller
from rozert_pay.payment.systems.muwe_spei.controller import muwe_spei_controller
from rozert_pay.payment.systems.nuvei.nuvei_controller import nuvei_controller
from rozert_pay.payment.systems.paycash import paycash_controller
from rozert_pay.payment.systems.paypal import paypal_controller
from rozert_pay.payment.systems.rozert_crypto.controller import rozert_crypto_controller
from rozert_pay.payment.systems.spei_stp.controller import spei_controller
from rozert_pay.payment.systems.stp_codi.controller import stp_codi_controller
from rozert_pay.payment.systems.worldpay.worldpay_controller import worldpay_controller

_V = TypedDict(
    "_V",
    {
        "name": str,
        "controller": PaymentSystemController[Any, Any],
    },
)


PAYMENT_SYSTEMS: dict[const.PaymentSystemType, _V] = {
    const.PaymentSystemType.PAYCASH: {
        "name": "PayCash",
        "controller": paycash_controller,
    },
    const.PaymentSystemType.STP_SPEI: {
        "name": "STP SPEI",
        "controller": spei_controller,
    },
    const.PaymentSystemType.STP_CODI: {
        "name": "STP CODI",
        "controller": stp_codi_controller,
    },
    const.PaymentSystemType.PAYPAL: {
        "name": "PayPal",
        "controller": paypal_controller,
    },
    const.PaymentSystemType.APPEX: {
        "name": "Appex",
        "controller": appex_controller,
    },
    const.PaymentSystemType.D24_MERCADOPAGO: {
        "name": "D24 MercadoPago",
        "controller": d24_mercadopago_controller,
    },
    const.PaymentSystemType.CONEKTA_OXXO: {
        "name": "Conekta Oxxo",
        "controller": conekta_oxxo_controller,
    },
    const.PaymentSystemType.BITSO_SPEI: {
        "name": "Bitso SPEI",
        "controller": bitso_spei_controller,
    },
    const.PaymentSystemType.MUWE_SPEI: {
        "name": "Rozert MUWE SPEI",
        "controller": muwe_spei_controller,
    },
    const.PaymentSystemType.CARDPAY_CARDS: {
        "name": "Cardpay Cards",
        "controller": cardpay_cards_controller,
    },
    const.PaymentSystemType.CARDPAY_APPLEPAY: {
        "name": "Cardpay Applepay",
        "controller": cardpay_applepay_controller,
    },
    const.PaymentSystemType.ILIXIUM: {
        "name": "Ilixium",
        "controller": ilixium_controller,
    },
    const.PaymentSystemType.WORLDPAY: {
        "name": "Worldpay",
        "controller": worldpay_controller,
    },
    const.PaymentSystemType.MPESA_MZ: {
        "name": "M-Pesa MZ",
        "controller": mpesa_mz_controller,
    },
    const.PaymentSystemType.NUVEI: {
        "name": "Nuvei",
        "controller": nuvei_controller,
    },
    const.PaymentSystemType.ROZERT_CRYPTO: {
        "name": "Rozert Crypto",
        "controller": rozert_crypto_controller,
    },
}
