from unittest import mock

import pytest
from rozert_pay.limits.models import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit
from rozert_pay.limits.services.limits import _notify_about_alerts
from rozert_pay.limits.const import (
    SLACK_CHANNEL_NAME_CRITICAL_LIMITS,
    SLACK_CHANNEL_NAME_REGULAR_LIMITS,
)
from rozert_pay.payment.models import Customer, Merchant, PaymentTransaction
from tests.factories import (
    CustomerLimitFactory,
    LimitAlertFactory,
    MerchantLimitFactory,
    PaymentTransactionFactory,
)


@pytest.mark.django_db
class TestNotifyAboutAlerts:
    @pytest.fixture
    def customer_limit_critical(self, customer: Customer) -> CustomerLimit:
        return CustomerLimitFactory.create(
            customer=customer,
            is_critical=True,
            decline_on_exceed=False,
        )

    @pytest.fixture
    def customer_limit_regular(self, customer: Customer) -> CustomerLimit:
        return CustomerLimitFactory.create(
            customer=customer,
            is_critical=False,
            decline_on_exceed=False,
        )

    @pytest.fixture
    def merchant_limit_critical(self, merchant: Merchant) -> MerchantLimit:
        return MerchantLimitFactory.create(
            merchant=merchant,
            is_critical=True,
            decline_on_exceed=False,
        )

    @pytest.fixture
    def merchant_limit_regular(self, merchant: Merchant) -> MerchantLimit:
        return MerchantLimitFactory.create(
            merchant=merchant,
            is_critical=False,
            decline_on_exceed=False,
        )

    @pytest.fixture
    def payment_transaction(self, customer: Customer) -> PaymentTransaction:
        return PaymentTransactionFactory.create(customer=customer)

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_empty_alerts_list_does_nothing(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
    ):
        _notify_about_alerts([])

        mock_construct_message.assert_not_called()
        mock_notify_slack.assert_not_called()

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_only_critical_alerts(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
        customer_limit_critical: CustomerLimit,
        payment_transaction: PaymentTransaction,
    ):
        mock_construct_message.return_value = "Critical alert message"

        critical_alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_critical,
            transaction=payment_transaction,
            extra={"test": "data"},
            is_active=True,
        )

        _notify_about_alerts([critical_alert])

        mock_construct_message.assert_called_once_with([critical_alert])
        mock_notify_slack.assert_called_once_with(
            kwargs={
                "message": "Critical alert message",
                "channel": SLACK_CHANNEL_NAME_CRITICAL_LIMITS,
            }
        )

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_only_regular_alerts(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
        customer_limit_regular: CustomerLimit,
        payment_transaction: PaymentTransaction,
    ):
        mock_construct_message.return_value = "Regular alert message"

        regular_alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_regular,
            transaction=payment_transaction,
            extra={"test": "data"},
            is_active=True,
        )

        _notify_about_alerts([regular_alert])

        mock_construct_message.assert_called_once_with([regular_alert])
        mock_notify_slack.assert_called_once_with(
            kwargs={
                "message": "Regular alert message",
                "channel": SLACK_CHANNEL_NAME_REGULAR_LIMITS,
            }
        )

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_mixed_critical_and_regular_alerts(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
        customer_limit_critical: CustomerLimit,
        customer_limit_regular: CustomerLimit,
        payment_transaction: PaymentTransaction,
    ):
        """Test notification for mixed critical and regular alerts."""
        mock_construct_message.side_effect = [
            "Critical alert message",
            "Regular alert message",
        ]

        critical_alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_critical,
            transaction=payment_transaction,
            extra={"critical": "data"},
            is_active=True,
        )

        regular_alert = LimitAlertFactory.create(
            customer_limit=customer_limit_regular,
            transaction=payment_transaction,
            extra={"regular": "data"},
            is_active=True,
        )

        _notify_about_alerts([critical_alert, regular_alert])

        assert mock_construct_message.call_count == 2
        mock_construct_message.assert_any_call([critical_alert])
        mock_construct_message.assert_any_call([regular_alert])

        assert mock_notify_slack.call_count == 2
        mock_notify_slack.assert_any_call(
            kwargs={
                "message": "Critical alert message",
                "channel": SLACK_CHANNEL_NAME_CRITICAL_LIMITS,
            }
        )
        mock_notify_slack.assert_any_call(
            kwargs={
                "message": "Regular alert message",
                "channel": SLACK_CHANNEL_NAME_REGULAR_LIMITS,
            }
        )

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_multiple_critical_alerts(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
        customer_limit_critical: CustomerLimit,
        merchant_limit_critical: MerchantLimit,
        payment_transaction: PaymentTransaction,
    ):
        """Test notification for multiple critical alerts."""
        mock_construct_message.return_value = "Multiple critical alerts message"

        customer_critical_alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_critical,
            transaction=payment_transaction,
            extra={"customer": "critical"},
            is_active=True,
        )

        merchant_critical_alert = LimitAlertFactory.create(
            merchant_limit=merchant_limit_critical,
            transaction=payment_transaction,
            extra={"merchant": "critical"},
            is_active=True,
        )

        alerts = [customer_critical_alert, merchant_critical_alert]
        _notify_about_alerts(alerts)

        mock_construct_message.assert_called_once_with(alerts)
        mock_notify_slack.assert_called_once_with(
            kwargs={
                "message": "Multiple critical alerts message",
                "channel": SLACK_CHANNEL_NAME_CRITICAL_LIMITS,
            }
        )

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_multiple_regular_alerts(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
        customer_limit_regular: CustomerLimit,
        merchant_limit_regular: MerchantLimit,
        payment_transaction: PaymentTransaction,
    ):
        """Test notification for multiple regular alerts."""
        mock_construct_message.return_value = "Multiple regular alerts message"

        customer_regular_alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_regular,
            transaction=payment_transaction,
            extra={"customer": "regular"},
            is_active=True,
        )

        merchant_regular_alert = LimitAlertFactory.create(
            merchant_limit=merchant_limit_regular,
            transaction=payment_transaction,
            extra={"merchant": "regular"},
            is_active=True,
        )

        alerts = [customer_regular_alert, merchant_regular_alert]
        _notify_about_alerts(alerts)

        mock_construct_message.assert_called_once_with(alerts)
        mock_notify_slack.assert_called_once_with(
            kwargs={
                "message": "Multiple regular alerts message",
                "channel": SLACK_CHANNEL_NAME_REGULAR_LIMITS,
            }
        )

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_alert_criticality_property_customer_limit(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
        customer_limit_critical: CustomerLimit,
        customer_limit_regular: CustomerLimit,
        payment_transaction: PaymentTransaction,
    ):
        """Test that alert criticality is determined by the associated limit's is_critical property."""
        mock_construct_message.side_effect = [
            "Critical message",
            "Regular message",
        ]

        # Create alerts with customer limits
        critical_alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_critical,
            transaction=payment_transaction,
            extra={"test": "critical"},
            is_active=True,
        )

        regular_alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_regular,
            transaction=payment_transaction,
            extra={"test": "regular"},
            is_active=True,
        )

        # Verify that the alert's is_critical property works correctly
        assert critical_alert.is_critical is True
        assert regular_alert.is_critical is False

        _notify_about_alerts([critical_alert, regular_alert])

        # Verify both channels are called
        assert mock_notify_slack.call_count == 2

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_alert_criticality_property_merchant_limit(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
        merchant_limit_critical: MerchantLimit,
        merchant_limit_regular: MerchantLimit,
        payment_transaction: PaymentTransaction,
    ):
        """Test that alert criticality is determined by the associated merchant limit's is_critical property."""
        mock_construct_message.side_effect = [
            "Critical message",
            "Regular message",
        ]

        # Create alerts with merchant limits
        critical_alert = LimitAlertFactory.create(
            merchant_limit=merchant_limit_critical,
            transaction=payment_transaction,
            extra={"test": "critical"},
            is_active=True,
        )

        regular_alert = LimitAlertFactory.create(
            merchant_limit=merchant_limit_regular,
            transaction=payment_transaction,
            extra={"test": "regular"},
            is_active=True,
        )

        # Verify that the alert's is_critical property works correctly
        assert critical_alert.is_critical is True
        assert regular_alert.is_critical is False

        _notify_about_alerts([critical_alert, regular_alert])

        # Verify both channels are called
        assert mock_notify_slack.call_count == 2

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_notification_separation_with_same_limit_types(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
        customer: Customer,
        payment_transaction: PaymentTransaction,
    ):
        """Test that alerts are properly separated even when coming from the same limit type."""
        # Create two customer limits with different criticality
        critical_limit = CustomerLimitFactory.create(
            customer=customer,
            is_critical=True,
            description="Critical limit",
        )

        regular_limit = CustomerLimitFactory.create(
            customer=customer,
            is_critical=False,
            description="Regular limit",
        )

        mock_construct_message.side_effect = [
            "Critical customer alert",
            "Regular customer alert",
        ]

        critical_alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=critical_limit,
            transaction=payment_transaction,
            extra={"limit": "critical_customer"},
            is_active=True,
        )

        regular_alert = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=regular_limit,
            transaction=payment_transaction,
            extra={"limit": "regular_customer"},
            is_active=True,
        )

        _notify_about_alerts([critical_alert, regular_alert])

        # Verify proper separation and notification
        mock_construct_message.assert_any_call([critical_alert])
        mock_construct_message.assert_any_call([regular_alert])

        mock_notify_slack.assert_any_call(
            kwargs={
                "message": "Critical customer alert",
                "channel": SLACK_CHANNEL_NAME_CRITICAL_LIMITS,
            }
        )
        mock_notify_slack.assert_any_call(
            kwargs={
                "message": "Regular customer alert",
                "channel": SLACK_CHANNEL_NAME_REGULAR_LIMITS,
            }
        )

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack.apply_async")
    @mock.patch("rozert_pay.limits.services.limits.construct_notification_message")
    def test_construct_notification_message_called_with_correct_alerts(
        self,
        mock_construct_message: mock.Mock,
        mock_notify_slack: mock.Mock,
        customer_limit_critical: CustomerLimit,
        customer_limit_regular: CustomerLimit,
        payment_transaction: PaymentTransaction,
    ):
        """Test that construct_notification_message is called with the correct alert lists."""
        mock_construct_message.return_value = "Test message"

        critical_alert_1 = LimitAlertFactory.create(
            merchant_limit=None,
            customer_limit=customer_limit_critical,
            transaction=payment_transaction,
            extra={"alert": "1"},
            is_active=True,
        )

        critical_alert_2 = LimitAlertFactory.create(
            customer_limit=customer_limit_critical,
            transaction=payment_transaction,
            extra={"alert": "2"},
            is_active=True,
        )

        regular_alert = LimitAlertFactory.create(
            customer_limit=customer_limit_regular,
            transaction=payment_transaction,
            extra={"alert": "3"},
            is_active=True,
        )

        all_alerts = [critical_alert_1, critical_alert_2, regular_alert]
        _notify_about_alerts(all_alerts)

        # Verify construct_notification_message is called with the right alert groups
        assert mock_construct_message.call_count == 2

        # Get the calls and verify the alert lists
        calls = mock_construct_message.call_args_list
        critical_call_alerts = calls[0][0][0]  # First positional argument of first call
        regular_call_alerts = calls[1][0][0]  # First positional argument of second call

        assert len(critical_call_alerts) == 2
        assert critical_alert_1 in critical_call_alerts
        assert critical_alert_2 in critical_call_alerts

        assert len(regular_call_alerts) == 1
        assert regular_alert in regular_call_alerts
