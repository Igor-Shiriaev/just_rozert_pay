from datetime import datetime
from decimal import Decimal

import pytest
from rozert_pay.limits.const import LimitPeriod
from rozert_pay.limits.models import CustomerLimit, MerchantLimit
from rozert_pay.limits.services.utils import construct_notification_message
from rozert_pay.payment.models import Customer, Merchant, PaymentTransaction, Wallet
from rozert_pay.settings import EXTERNAL_ROZERT_HOST
from tests.factories import (
    CustomerLimitFactory,
    LimitAlertFactory,
    MerchantLimitFactory,
    PaymentTransactionFactory,
)


@pytest.mark.django_db
class TestConstructNotificationMessage:
    @pytest.fixture
    def customer_limit_critical(self, customer: Customer) -> CustomerLimit:
        return CustomerLimitFactory.create(
            customer=customer,
            is_critical=True,
            description="Critical customer limit description",
        )

    @pytest.fixture
    def customer_limit_regular(self, customer: Customer) -> CustomerLimit:
        return CustomerLimitFactory.create(
            customer=customer,
            is_critical=False,
            description="Regular customer limit description",
        )

    @pytest.fixture
    def merchant_limit_critical(
        self, merchant: Merchant, wallet: Wallet
    ) -> MerchantLimit:
        return MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            is_critical=True,
            description="Critical merchant limit description",
        )

    @pytest.fixture
    def merchant_limit_regular(
        self, merchant: Merchant, wallet: Wallet
    ) -> MerchantLimit:
        return MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            is_critical=False,
            description="Regular merchant limit description",
        )

    @pytest.fixture
    def payment_transaction(self, customer: Customer) -> PaymentTransaction:
        return PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("100.00"),
        )

    def test_single_customer_limit_critical_alert(
        self,
        customer_limit_critical: CustomerLimit,
        payment_transaction: PaymentTransaction,
    ):
        alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_critical,
            transaction=payment_transaction,
            extra={"min_operation_amount": "Amount too low"},
            is_active=True,
        )

        message = construct_notification_message([alert])

        expected_parts = [
            f"Trigger time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "Категория: 💢 Critical",
            "Описание: Critical customer limit description",
            "Wallet name: N/A",
            "Тип: Customer Limit",
            "Period: 1h",
            f"ID: <{EXTERNAL_ROZERT_HOST}/admin/limits/limitalert/{alert.id}/change/|{alert.id}>",
        ]

        for part in expected_parts:
            assert part in message

    def test_single_customer_limit_regular_alert(
        self,
        customer_limit_regular: CustomerLimit,
        payment_transaction: PaymentTransaction,
    ):
        alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_regular,
            transaction=payment_transaction,
            extra={"max_operation_amount": "Amount too high"},
            is_active=True,
        )
        alert.created_at = datetime(2024, 1, 15, 14, 45, 30)
        alert.save()

        message = construct_notification_message([alert])

        expected_parts = [
            "Время срабатывания: 2024-01-15 14:45:30 UTC",
            "Категория: Regular",
            "Описание: Regular customer limit description",
            "Wallet name: N/A",
            "Тип: Customer Limit",
            f"ID: <{EXTERNAL_ROZERT_HOST}/admin/limits/limitalert/{alert.id}/change/|{alert.id}>",
        ]

        for part in expected_parts:
            assert part in message

    def test_single_merchant_limit_critical_alert(
        self,
        merchant_limit_critical: MerchantLimit,
        payment_transaction: PaymentTransaction,
    ):
        alert = LimitAlertFactory.create(
            customer_limit=None,
            merchant_limit=merchant_limit_critical,
            transaction=payment_transaction,
            extra={"total_amount_deposits_period": "Too many deposits"},
            is_active=True,
        )

        message = construct_notification_message([alert])

        assert merchant_limit_critical.wallet
        expected_parts = [
            f"Время срабатывания: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "Категория: 💢 Critical",
            "Описание: Critical merchant limit description",
            f"Wallet name: {merchant_limit_critical.wallet.name}",
            f"Тип: {merchant_limit_critical.scope}",
            f"ID: <{EXTERNAL_ROZERT_HOST}/admin/limits/limitalert/{alert.id}/change/|{alert.id}>",
        ]

        for part in expected_parts:
            assert part in message

    def test_single_merchant_limit_regular_alert(
        self,
        merchant_limit_regular: MerchantLimit,
        payment_transaction: PaymentTransaction,
    ):
        alert = LimitAlertFactory.create(
            customer_limit=None,
            merchant_limit=merchant_limit_regular,
            transaction=payment_transaction,
            extra={"max_successful_deposits": "Deposit limit exceeded"},
            is_active=True,
        )

        message = construct_notification_message([alert])

        assert merchant_limit_regular.wallet
        expected_parts = [
            f"Trigger time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "Category: Regular",
            "Description: Regular merchant limit description",
            f"Wallet name: {merchant_limit_regular.wallet.name}",
            f"Тип: {merchant_limit_regular.scope}",
            f"ID: <{EXTERNAL_ROZERT_HOST}/admin/limits/limitalert/{alert.id}/change/|{alert.id}>",
        ]

        for part in expected_parts:
            assert part in message

    def test_multiple_alerts_message_format(
        self,
        customer_limit_critical: CustomerLimit,
        merchant_limit_regular: MerchantLimit,
        payment_transaction: PaymentTransaction,
    ):
        alert1 = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_critical,
            transaction=payment_transaction,
            extra={"test": "alert1"},
            is_active=True,
        )

        alert2 = LimitAlertFactory.create(
            customer_limit=None,
            merchant_limit=merchant_limit_regular,
            transaction=payment_transaction,
            extra={"test": "alert2"},
            is_active=True,
        )

        message = construct_notification_message([alert1, alert2])

        assert str(alert1.id) in message
        assert str(alert2.id) in message
        assert "💢 Critical" in message
        assert "Regular" in message

        alert_sections = message.split("\n\n")
        assert len(alert_sections) == 2

    def test_merchant_limit_without_wallet(self, merchant: Merchant):
        merchant_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=None,
            is_critical=False,
            description="Merchant limit without wallet",
        )

        payment_transaction = PaymentTransactionFactory.create()

        alert = LimitAlertFactory.create(
            merchant_limit=merchant_limit,
            transaction=payment_transaction,
            extra={"test": "no_wallet"},
            is_active=True,
        )

        message = construct_notification_message([alert])

        assert "Wallet name: N/A" in message

    def test_merchant_limit_without_description(
        self, merchant: Merchant, wallet: Wallet
    ):
        merchant_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            is_critical=False,
            description="",
        )

        payment_transaction = PaymentTransactionFactory.create()

        alert = LimitAlertFactory.create(
            customer_limit=None,
            merchant_limit=merchant_limit,
            transaction=payment_transaction,
            extra={"test": "no_description"},
            is_active=True,
        )

        message = construct_notification_message([alert])
        assert "Description: Merchant Limit" in message  # Default description

    def test_empty_alerts_list(self):
        message = construct_notification_message([])
        assert message == ""

    def test_period_display_formatting(self, customer: Customer):
        periods_to_test = [
            LimitPeriod.ONE_HOUR,
            LimitPeriod.TWENTY_FOUR_HOURS,
            LimitPeriod.BEGINNING_OF_HOUR,
            LimitPeriod.BEGINNING_OF_DAY,
        ]

        for period in periods_to_test:
            customer_limit = CustomerLimitFactory.create(
                customer=customer,
                period=period,
                description=f"Limit with {period} period",
            )

            payment_transaction = PaymentTransactionFactory.create(customer=customer)

            alert = LimitAlertFactory.create(
                customer_limit=customer_limit,
                transaction=payment_transaction,
                extra={"test": f"period_{period}"},
                is_active=True,
            )

            message = construct_notification_message([alert])

            assert f"Period: {period}" in message
