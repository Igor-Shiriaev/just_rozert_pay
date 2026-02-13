import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, override_settings
from django.urls import reverse
from rozert_pay.payment.admin import (
    IncomingCallbackAdmin,
    PaymentSystemAdmin,
    PaymentTransactionAdmin,
    PaymentTransactionEventLogAdmin,
)
from rozert_pay.payment.models import (
    IncomingCallback,
    PaymentSystem,
    PaymentTransaction,
    PaymentTransactionEventLog,
)
from tests.factories import (
    CurrencyWalletFactory,
    CustomerFactory,
    CustomerLimitFactory,
    IncomingCallbackFactory,
    LimitAlertFactory,
    MerchantFactory,
    MerchantLimitFactory,
    PaymentSystemFactory,
    PaymentTransactionEventLogFactory,
    PaymentTransactionFactory,
    UserFactory,
    WalletFactory,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestIncomingCallbackAdmin:
    @pytest.fixture
    def admin(self):
        return IncomingCallbackAdmin(model=IncomingCallback, admin_site=AdminSite())

    def test_links(self, admin):
        transaction = PaymentTransactionFactory.create()
        incoming_callback = IncomingCallbackFactory.create(
            transaction=transaction,
        )

        links_html = admin.links(incoming_callback)

        expected_links = [
            (
                f"/admin/payment/paymentsystem/?id={incoming_callback.system_id}",
                "System",
            ),
            (
                f"/admin/payment/paymenttransactioneventlog/"
                f"?incoming_callback_id={incoming_callback.id}",
                "Logs",
            ),
            (
                f"/admin/payment/paymenttransaction/?id={transaction.id}",
                "Transaction",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html
            assert text in links_html

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == 3
        assert links_html.count("<a href=") == 3

    def test_links_without_transaction(self, admin):
        incoming_callback = IncomingCallbackFactory.create(
            transaction=None,
        )

        links_html = admin.links(incoming_callback)

        expected_links = [
            (
                f"/admin/payment/paymentsystem/?id={incoming_callback.system_id}",
                "System",
            ),
            (
                f"/admin/payment/paymenttransactioneventlog/"
                f"?incoming_callback_id={incoming_callback.id}",
                "Logs",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html
            assert text in links_html

        assert "?paymenttransaction/?id=" not in links_html

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == 2
        assert links_html.count("<a href=") == 2


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestPaymentTransactionEventLogAdmin:
    @pytest.fixture
    def admin(self):
        return PaymentTransactionEventLogAdmin(
            model=PaymentTransactionEventLog, admin_site=AdminSite()
        )

    def test_links(self, admin):
        transaction = PaymentTransactionFactory.create()
        event_log = PaymentTransactionEventLogFactory.create(
            transaction=transaction,
            incoming_callback=None,
        )

        links_html = admin.links(event_log)

        expected_links = [
            (
                f"/admin/payment/paymenttransaction/?id={event_log.transaction_id}",
                "Transaction",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html
            assert text in links_html

        assert not links_html.startswith("<ul>")
        assert not links_html.endswith("</ul>")
        assert links_html.count("<li>") == 0
        assert links_html.count("<a href=") == 1

        assert "/admin/payment/incomingcallback/?id=" not in links_html


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestPaymentSystemAdmin:
    @pytest.fixture
    def admin(self):
        return PaymentSystemAdmin(model=PaymentSystem, admin_site=AdminSite())

    def test_links(self, admin):
        payment_system = PaymentSystemFactory.create()

        links_html = admin.links(payment_system)

        expected_links = [
            (
                f"/admin/payment/incomingcallback/?system_id={payment_system.id}",
                "Incoming Callbacks",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html
            assert text in links_html

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == 3
        assert links_html.count("<a href=") == 3

        assert "/admin/payment/incomingcallback/?id=" not in links_html


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestPaymentTransactionAdmin:
    @pytest.fixture
    def admin(self):
        return PaymentTransactionAdmin(model=PaymentTransaction, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_links_with_full_relations(self, admin, settings):
        merchant = MerchantFactory.create()
        wallet = WalletFactory.create(merchant=merchant)
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        customer = CustomerFactory.create()
        transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet, customer=customer
        )

        customer_limit = CustomerLimitFactory.create(customer=customer)
        wallet_limit = MerchantLimitFactory.create(wallet=wallet)
        merchant_limit = MerchantLimitFactory.create(merchant=merchant)
        LimitAlertFactory.create(transaction=transaction, customer_limit=customer_limit)
        LimitAlertFactory.create(transaction=transaction, merchant_limit=wallet_limit)
        LimitAlertFactory.create(transaction=transaction, merchant_limit=merchant_limit)

        links_html = admin.links(transaction)

        expected_links = [
            (
                reverse("admin:payment_paymenttransactioneventlog_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Logs",
            ),
            (
                reverse("admin:payment_incomingcallback_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Incoming callbacks",
            ),
            (
                reverse("admin:payment_wallet_change", args=[wallet.pk]),
                "Wallet",
            ),
            (
                f"{settings.BETMASTER_BASE_URL}admin/payment/paymenttransaction/"
                f"?id_in_payment_system={transaction.uuid}",
                "Betmaster transactions",
            ),
            (
                reverse("admin:limits_customerlimit_changelist")
                + f"?id__in={customer_limit.id}",
                "Triggered Customer Limits",
            ),
            (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={wallet_limit.id}",
                "Triggered Wallet Limits",
            ),
            (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={merchant_limit.id}",
                "Triggered Merchant Limits",
            ),
            (
                reverse("admin:limits_limitalert_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Triggered Limit Alerts",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html, f"Link {url} not found in links_html"
            assert text in links_html, f"Text {text} not found in links_html"

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == len(
            expected_links
        ), f"Expected {len(expected_links)} links, but found {links_html.count('<li>')}"

    def test_links_without_customer(self, admin, settings):
        merchant = MerchantFactory.create()
        wallet = WalletFactory.create(merchant=merchant)
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet, customer=None
        )

        wallet_limit = MerchantLimitFactory.create(wallet=wallet)
        merchant_limit = MerchantLimitFactory.create(merchant=merchant)
        LimitAlertFactory.create(transaction=transaction, merchant_limit=wallet_limit)
        LimitAlertFactory.create(transaction=transaction, merchant_limit=merchant_limit)

        links_html = admin.links(transaction)

        expected_links = [
            (
                reverse("admin:payment_paymenttransactioneventlog_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Logs",
            ),
            (
                reverse("admin:payment_incomingcallback_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Incoming callbacks",
            ),
            (
                reverse("admin:payment_wallet_change", args=[wallet.pk]),
                "Wallet",
            ),
            (
                f"{settings.BETMASTER_BASE_URL}admin/payment/paymenttransaction/"
                f"?id_in_payment_system={transaction.uuid}",
                "Betmaster transactions",
            ),
            (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={wallet_limit.id}",
                "Triggered Wallet Limits",
            ),
            (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={merchant_limit.id}",
                "Triggered Merchant Limits",
            ),
            (
                reverse("admin:limits_limitalert_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Triggered Limit Alerts",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html, f"Link {url} not found in links_html"
            assert text in links_html, f"Text {text} not found in links_html"

        assert (
            "?customer__id__exact=" not in links_html
        ), "Customer link found when it shouldn't be"
        assert (
<<<<<<< Updated upstream
            "Triggered Customer Limits" not in links_html
        ), "Triggered Customer Limits text found when it shouldn't be"
=======
            "Customer Limits" not in links_html
        ), "Customer Limits text found when it shouldn't be"
>>>>>>> Stashed changes

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == len(
            expected_links
        ), f"Expected {len(expected_links)} links, but found {links_html.count('<li>')}"

    @override_settings(IS_PRODUCTION=True)
    def test_has_change_permission_production(self, admin, admin_request):
        assert not admin.has_change_permission(admin_request)

    @override_settings(IS_PRODUCTION=False)
    def test_has_change_permission_development(self, admin, admin_request):
        assert admin.has_change_permission(admin_request)
