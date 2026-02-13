from django.urls import path
from rest_framework.routers import DefaultRouter
from rozert_pay.payment.api_v1 import views
from rozert_pay.payment.systems.appex.appex_views import AppexViewSet
from rozert_pay.payment.systems.bitso_spei.bitso_spei_views import BitsoSpeiViewSet
from rozert_pay.payment.systems.cardpay_systems.cardpay_applepay.views import (
    CardpayApplepayViewSet,
)
from rozert_pay.payment.systems.cardpay_systems.cardpay_cards.views import (
    CardpayBankcardViewSet,
)
from rozert_pay.payment.systems.conekta.conekta_oxxo import ConektaOxxoViewSet
from rozert_pay.payment.systems.d24_mercadopago.views import D24MercadoPagoViewSet
from rozert_pay.payment.systems.ilixium.ilixium_views import IlixiumViewSet
from rozert_pay.payment.systems.mpesa_mz.views import MpesaMzViewSet
from rozert_pay.payment.systems.muwe_spei.views import MuweSpeiViewSet
from rozert_pay.payment.systems.nuvei.nuvei_views import NuveiViewSet
from rozert_pay.payment.systems.paycash import PaycashViewSet
from rozert_pay.payment.systems.paypal import PaypalViewSet
from rozert_pay.payment.systems.spei_stp.views import StpSpeiViewSet
from rozert_pay.payment.systems.stp_codi.views import StpCodiViewSet
from rozert_pay.payment.systems.worldpay.worldpay_views import WorldpayViewSet

router = DefaultRouter()

router.register(r"wallet", views.WalletViewSet, basename="wallet")
router.register(r"transaction", views.TransactionViewSet, basename="transaction")
router.register(r"card-bin-data", views.CardBinDataViewSet, basename="card-bin-data")

# Payment system specific views.
router.register("stp-codi", StpCodiViewSet, basename="stp-codi")
router.register("paypal", PaypalViewSet, basename="paypal")
router.register("bitso-spei", BitsoSpeiViewSet, basename="bitso-spei")
router.register("d24-mercadopago", D24MercadoPagoViewSet, basename="d24-mercadopago")
router.register("paycash", PaycashViewSet, basename="paycash")
router.register("appex", AppexViewSet, basename="appex")
router.register("conekta-oxxo", ConektaOxxoViewSet, basename="conekta-oxxo")
router.register("cardpay-cards", CardpayBankcardViewSet, basename="cardpay-cards")
router.register("cardpay-applepay", CardpayApplepayViewSet, basename="cardpay-applepay")
router.register("worldpay", WorldpayViewSet, basename="worldpay")
router.register("nuvei", NuveiViewSet, basename="nuvei")

router.register("stp-spei", StpSpeiViewSet, basename="stp-spei")
router.register("muwe-spei", MuweSpeiViewSet, basename="muwe-spei")
router.register("ilixium", IlixiumViewSet, basename="ilixium")
router.register("mpesa-mz", MpesaMzViewSet, basename="mpesa-mz")

urlpatterns = router.urls + [
    path("callback/<str:system>/", views.CallbackView.as_view(), name="callback"),
    path("redirect/<str:system>/", views.RedirectView.as_view(), name="redirect"),
]
