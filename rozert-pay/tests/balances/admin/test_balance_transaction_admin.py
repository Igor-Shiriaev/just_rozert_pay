from decimal import Decimal

import pytest
from django.contrib.admin.sites import AdminSite
from django.http import HttpRequest
from django.test import RequestFactory
from rozert_pay.balances.admin import BalanceTransactionAdmin
from rozert_pay.balances.const import BalanceTransactionType, InitiatorType
from rozert_pay.balances.models import BalanceTransaction
from tests.factories import BalanceTransactionFactory, PaymentTransactionFactory


@pytest.mark.django_db
class TestBalanceTransactionAdmin:
    @pytest.fixture
    def admin(self) -> BalanceTransactionAdmin:
        return BalanceTransactionAdmin(model=BalanceTransaction, admin_site=AdminSite())

    @pytest.fixture
    def http_request(self) -> HttpRequest:
        return RequestFactory().get("/admin")

    def test_short_id(self, admin: BalanceTransactionAdmin):
        transaction = BalanceTransactionFactory.create()
        short_id_str = admin.short_id(transaction)

        expected_start = str(transaction.id).split("-")[0]
        assert short_id_str == f"{expected_start}..."

    def test_info_positive_amount(self, admin: BalanceTransactionAdmin):
        transaction = BalanceTransactionFactory.create(
            amount=Decimal("150.75"),
            operational_before=Decimal("1000.00"),
            operational_after=Decimal("1150.75"),
            type=BalanceTransactionType.OPERATION_CONFIRMED,
            initiator=InitiatorType.SYSTEM,
        )
        info_html = admin.info(transaction)

        assert (
            "<li>Type: <b>Successful deposit. Increases operational and pending balances.</b></li>"
            in info_html
        )
        assert '<li>Amount: <b style="color: green;">+150.75</b></li>' in info_html
        assert "<li>Balance: 1000.00 → <b>1150.75</b></li>" in info_html
        assert (
            f"<li>Wallet: {transaction.currency_wallet.wallet.name} ({transaction.currency_wallet.currency})</li>"
            in info_html
        )
        assert "<li>Initiator: System</li>" in info_html
        assert info_html.startswith(
            '<ul style="margin:0; padding-left:15px; white-space:nowrap;">'
        )

    def test_info_negative_amount(self, admin: BalanceTransactionAdmin):
        transaction = BalanceTransactionFactory.create(
            amount=Decimal("-50.00"),
            operational_before=Decimal("1150.75"),
            operational_after=Decimal("1100.75"),
            type=BalanceTransactionType.FEE,
        )
        info_html = admin.info(transaction)

        assert '<li>Amount: <b style="color: red;">-50.00</b></li>' in info_html
        assert "<li>Balance: 1150.75 → <b>1100.75</b></li>" in info_html

    def test_links_with_payment_transaction(self, admin: BalanceTransactionAdmin):
        payment_transaction = PaymentTransactionFactory.create()
        balance_transaction = BalanceTransactionFactory.create(
            payment_transaction=payment_transaction
        )

        links_html = admin.links(balance_transaction)

        wallet_url = f"/admin/payment/currencywallet/{balance_transaction.currency_wallet.pk}/change/"
        payment_tx_url = (
            f"/admin/payment/paymenttransaction/{payment_transaction.pk}/change/"
        )

        assert wallet_url in links_html
        assert "Currency Wallet" in links_html
        assert payment_tx_url in links_html
        assert "Payment Transaction" in links_html

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == 2

    def test_links_without_payment_transaction(self, admin: BalanceTransactionAdmin):
        balance_transaction = BalanceTransactionFactory.create(payment_transaction=None)

        links_html = admin.links(balance_transaction)

        wallet_url = f"/admin/payment/currencywallet/{balance_transaction.currency_wallet.pk}/change/"

        assert wallet_url in links_html
        assert "Currency Wallet" in links_html
        assert "/admin/payment/paymenttransaction/" not in links_html

        assert not links_html.startswith("<ul>")
        assert links_html.startswith("<a href=")

    def test_permissions(
        self, admin: BalanceTransactionAdmin, http_request: HttpRequest
    ):
        transaction = BalanceTransactionFactory.create()

        assert admin.has_add_permission(http_request) is False
        assert admin.has_change_permission(http_request, transaction) is False
        assert admin.has_change_permission(http_request) is False
        assert admin.has_delete_permission(http_request, transaction) is False
        assert admin.has_delete_permission(http_request) is False
