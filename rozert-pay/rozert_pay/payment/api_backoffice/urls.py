from rest_framework.routers import DefaultRouter
from rozert_pay.payment.api_backoffice import views

router = DefaultRouter()
router.include_format_suffixes = False

router.register(r"wallet", views.CabinetWalletViewSet, basename="backoffice-wallet")
router.register(
    r"transaction", views.CabinetTransactionViewSet, basename="backoffice-transaction"
)
router.register(
    r"deposit-account",
    views.CabinetDepositAccountViewSet,
    basename="backoffice-deposit_account",
)
router.register(
    r"callback",
    views.CabinetCallbackViewSet,
    basename="callback",
)
router.register("alerts", views.CabinetAlertViewSet, "alerts")
router.register(
    r"merchant-profile",
    views.MerchantProfileViewSet,
    basename="backoffice-merchant-profile",
)

urlpatterns = router.urls
