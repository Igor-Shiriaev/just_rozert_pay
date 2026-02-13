import pytest
from django.urls import reverse
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.limit_alert import LimitAlert
from rozert_pay.limits.models.merchant_limits import (
    LimitType,
    MerchantLimit,
    MerchantLimitScope,
)
from rozert_pay.payment.api_backoffice.serializers import LimitAlertSerializer
from rozert_pay.payment.models import PaymentTransaction
from tests.factories import (
    CustomerLimitFactory,
    LimitAlertFactory,
    MerchantLimitFactory,
    PaymentTransactionFactory,
)


@pytest.mark.django_db
class TestLimitAlertSerializerLogic:
    def test_get_description(self):
        serializer = LimitAlertSerializer()

        merchant_limit: MerchantLimit = MerchantLimitFactory.build(
            description="Merchant Limit Description"
        )
        alert_with_merchant_limit: LimitAlert = LimitAlertFactory.build(
            merchant_limit=merchant_limit, customer_limit=None
        )
        assert (
            serializer.get_description(alert_with_merchant_limit)
            == "Merchant Limit Description"
        )

        merchant_limit_no_desc: MerchantLimit = MerchantLimitFactory.build(
            description=""
        )
        alert_with_merchant_limit_no_desc: LimitAlert = LimitAlertFactory.build(
            merchant_limit=merchant_limit_no_desc, customer_limit=None
        )
        assert serializer.get_description(alert_with_merchant_limit_no_desc) == "-"

        # Case without customer_limit and merchant_limit (N/A)
        alert_no_limits = LimitAlert()
        assert serializer.get_description(alert_no_limits) == "-"

    def test_get_limit_url(self):
        serializer = LimitAlertSerializer()

        customer_limit: CustomerLimit = CustomerLimitFactory.build(id=1)
        alert_with_customer_limit: LimitAlert = LimitAlertFactory.build(
            customer_limit=customer_limit, merchant_limit=None
        )
        expected_customer_url = reverse(
            "admin:limits_customerlimit_change", args=[customer_limit.pk]
        )
        assert (
            serializer.get_limit_url(alert_with_customer_limit) == expected_customer_url
        )

        merchant_limit: MerchantLimit = MerchantLimitFactory.build(id=2)
        alert_with_merchant_limit: LimitAlert = LimitAlertFactory.build(
            merchant_limit=merchant_limit, customer_limit=None
        )
        expected_merchant_url = reverse(
            "admin:limits_merchantlimit_change", args=[merchant_limit.pk]
        )
        assert (
            serializer.get_limit_url(alert_with_merchant_limit) == expected_merchant_url
        )

        alert_no_limits = LimitAlert()
        assert serializer.get_limit_url(alert_no_limits) == "-"

    def test_get_transaction_url(self):
        serializer = LimitAlertSerializer()

        transaction: PaymentTransaction = PaymentTransactionFactory.create()
        alert_with_transaction: LimitAlert = LimitAlertFactory.build(
            transaction=transaction
        )
        expected_url = reverse(
            "admin:payment_paymenttransaction_change", args=[transaction.pk]
        )
        assert serializer.get_transaction_url(alert_with_transaction) == expected_url

        alert_no_transaction = LimitAlert()
        assert serializer.get_transaction_url(alert_no_transaction) == "-"


@pytest.mark.django_db
class TestMerchantLimitModel:
    def test_str_method(self):
        limit: MerchantLimit = MerchantLimitFactory.create(
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            scope=MerchantLimitScope.MERCHANT,
        )
        expected_str = f"MerchantLimit(id={limit.id}, type={limit.limit_type}, scope={limit.scope})"
        assert str(limit) == expected_str
