from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone
from rozert_pay.common import const
from rozert_pay.limits import const as limit_const
from rozert_pay.limits.const import LimitPeriod
from rozert_pay.limits.models.common import LimitCategory
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.limit_alert import LimitAlert
from rozert_pay.limits.models.merchant_limits import (
    LimitType,
    MerchantLimit,
    MerchantLimitScope,
)
from rozert_pay.limits.services import limits
from rozert_pay.payment.factories import get_payment_system_controller
from rozert_pay.payment.models import (
    Customer,
    Merchant,
    PaymentTransactionEventLog,
    Wallet,
)
from rozert_pay.payment.tasks import process_transaction
from tests.factories import (
    CurrencyWalletFactory,
    CustomerFactory,
    CustomerLimitFactory,
    LimitAlertFactory,
    MerchantLimitFactory,
    PaymentTransactionFactory,
)
from tests.limits.conftest import create_currency_wallet_from_second_wallet


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestCustomerLimits:
    @pytest.fixture
    def customer_limit(self, customer):
        return CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=3,
            max_failed_operations=2,
            min_operation_amount=10,
            max_operation_amount=1000,
            total_successful_amount=2000,
            decline_on_exceed=True,
            is_critical=True,
            category=LimitCategory.BUSINESS,
        )

    def test_clean_validation(
        self,
        customer,
        customer_limit: CustomerLimit,
    ):
        with pytest.raises(ValidationError, match=".*already exists.*"):
            duplicate_limit = CustomerLimitFactory.create(
                customer=customer,
                period=LimitPeriod.ONE_HOUR,
                max_successful_operations=3,
                max_failed_operations=2,
                min_operation_amount=10,
                max_operation_amount=1000,
                total_successful_amount=2000,
                decline_on_exceed=True,
                is_critical=True,
            )
            duplicate_limit.clean()

        with pytest.raises(ValidationError, match=".*must be set*"):
            limit_without_required_params = CustomerLimitFactory.create(
                customer=customer,
                period=LimitPeriod.TWENTY_FOUR_HOURS,
                max_successful_operations=None,
                max_failed_operations=None,
                min_operation_amount=None,
                max_operation_amount=None,
                total_successful_amount=None,
                decline_on_exceed=True,
                is_critical=True,
            )
            limit_without_required_params.clean()

    def test_min_operation_amount(
        self,
        customer_limit: CustomerLimit,
    ):
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)
        assert is_declined

        payment_transaction.refresh_from_db()

        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.customer_limit == customer_limit
        assert alert.extra == {
            "Minimum amount for a single operation": "Transaction amount 9.99 is less than limit 10.00",
        }

    def test_max_operation_amount(
        self,
        customer_limit: CustomerLimit,
    ):
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=Decimal("1000.01"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.customer_limit == customer_limit
        assert alert.extra == {
            "Maximum amount for a single operation": "Transaction amount 1000.01 is greater than limit 1000.00",
        }

    def test_max_successful_operations(
        self,
        customer_limit: CustomerLimit,
    ):
        PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=100,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=100,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=100,
            status=const.TransactionStatus.SUCCESS,
        )
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=100,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.customer_limit == customer_limit
        assert alert.extra == {
            "max_successful_operations": "Number of successful transactions 3 has exceeded limit 3",
        }

    def test_max_failed_operations(
        self,
        customer_limit: CustomerLimit,
    ):
        PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=100,
            status=const.TransactionStatus.FAILED,
        )
        PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=100,
            status=const.TransactionStatus.FAILED,
        )
        PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=100,
            status=const.TransactionStatus.FAILED,
        )
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=100,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.customer_limit == customer_limit
        assert alert.extra == {
            "max_failed_operations": "Number of failed transactions 3 has exceeded limit 2",
        }

    def test_total_successful_amount(
        self,
        customer_limit: CustomerLimit,
    ):
        PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=1700,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=Decimal("290.01"),
            status=const.TransactionStatus.SUCCESS,
        )
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=10,
            status=const.TransactionStatus.PENDING,
        )

        limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.customer_limit == customer_limit
        assert alert.extra == {
            "total_successful_amount": (
                "Total successful amount 1990.01 with current transaction amount 10 "
                "is greater than limit 2000.00"
            ),
        }

    def test_active_limit(
        self,
        customer_limit: CustomerLimit,
    ):
        customer_limit.active = False
        customer_limit.save()

        payment_transaction = PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )

        limits._process_transaction_limits(payment_transaction)
        assert not LimitAlert.objects.exists()

        customer_limit.active = True
        customer_limit.save()

        payment_transaction = PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )

        limits._process_transaction_limits(payment_transaction)
        assert LimitAlert.objects.exists()

    def test_in_celery_task(
        self,
        customer_limit: CustomerLimit,
    ):
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )
        process_transaction.apply(kwargs={"transaction_id": payment_transaction.id})

        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.FAILED
        assert LimitAlert.objects.exists()
        assert LimitAlert.objects.count() == 1
        assert PaymentTransactionEventLog.objects.count() == 2
        decline_log = PaymentTransactionEventLog.objects.get(
            event_type=const.EventType.DECLINED_BY_LIMIT
        )
        assert decline_log.extra == {
            "0": {
                limit_const.VERBOSE_NAME_MIN_AMOUNT_SINGLE_OPERATION: "Transaction amount 9.99 is less than limit 10.00",
            },
        }

        customer_limit.decline_on_exceed = False
        customer_limit.save()

        # Limit doesn't decline transaction, but creates alert
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer_limit.customer,
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )
        controller = get_payment_system_controller(payment_transaction.system)
        with mock.patch.object(controller, "run_deposit") as run_deposit_mock:
            process_transaction.apply(kwargs={"transaction_id": payment_transaction.id})
            assert run_deposit_mock.call_count == 1

        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        assert LimitAlert.objects.count() == 2
        assert (
            PaymentTransactionEventLog.objects.filter(
                event_type=const.EventType.DECLINED_BY_LIMIT
            ).count()
            == 1
        )

    def test_customer_limit_mismatching_customer_trx_customer(
        self,
        customer,
    ):
        customer2 = CustomerFactory.create()

        CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=1,
            decline_on_exceed=True,
        )

        payment_transaction_for_customer2 = PaymentTransactionFactory.create(
            customer=customer2,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined, triggered_alerts = limits._process_transaction_limits(
            payment_transaction_for_customer2
        )

        assert not is_declined
        assert not triggered_alerts
        assert not LimitAlert.objects.exists()

        customer_limit_for_customer2 = CustomerLimitFactory.create(
            customer=customer2,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=1,
            decline_on_exceed=True,
        )

        PaymentTransactionFactory.create(
            customer=customer2,
            amount=Decimal("100"),
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction_for_customer2_again = PaymentTransactionFactory.create(
            customer=customer2,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined_2, triggered_alerts_2 = limits._process_transaction_limits(
            payment_transaction_for_customer2_again
        )

        assert is_declined_2
        assert len(triggered_alerts_2) == 1
        assert triggered_alerts_2[0].customer_limit == customer_limit_for_customer2


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestMerchantScopeLimits:
    def test_min_operation_amount(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Minimum amount for a single operation": "Transaction amount 9.99 is less than limit 10.00",
            "scope": "merchant",
        }

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            status=const.TransactionStatus.PENDING,
        )
        is_declined, _ = limits._process_transaction_limits(payment_transaction)
        assert not is_declined

    def test_max_operation_amount(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        merchant_scope_limit.limit_type = LimitType.MAX_AMOUNT_SINGLE_OPERATION
        merchant_scope_limit.save()

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("100.01"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Maximum amount for a single operation": "Transaction amount 100.01 is greater than limit 100.00",
            "scope": "merchant",
        }

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )
        is_declined, _ = limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert not is_declined

    def test_max_successful_deposits(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        merchant_scope_limit.limit_type = LimitType.MAX_SUCCESSFUL_DEPOSITS
        merchant_scope_limit.save()

        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_scope_limit.merchant
            ),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.SUCCESS
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Maximum number of successful deposits per period": "Number of successful deposits 3 has exceeded limit 3",
            "scope": "merchant",
        }

    def test_max_overall_decline_percent(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        merchant_scope_limit.limit_type = LimitType.MAX_OVERALL_DECLINE_PERCENT
        merchant_scope_limit.save()

        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_scope_limit.merchant
            ),
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.FAILED
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Maximum decline percentage per period": "Failed transactions percent 33.33 is greater than limit 33.32",
            "scope": "merchant",
        }

    def test_max_withdrawal_decline_percent(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        merchant_scope_limit.limit_type = LimitType.MAX_WITHDRAWAL_DECLINE_PERCENT
        merchant_scope_limit.save()

        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_scope_limit.merchant
            ),
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.FAILED
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Maximum withdrawal decline percentage per period": "Failed withdrawals percent 33.33 is greater than limit 33.32",
            "scope": "merchant",
        }

    def test_max_deposit_decline_percent(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        merchant_scope_limit.limit_type = LimitType.MAX_DEPOSIT_DECLINE_PERCENT
        merchant_scope_limit.save()

        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_scope_limit.merchant
            ),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.FAILED,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.FAILED
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Maximum deposit decline percentage per period": "Failed deposits percent 40.00 is greater than limit 39.99",
            "scope": "merchant",
        }

    def test_total_amount_deposits_period(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        merchant_scope_limit.limit_type = LimitType.TOTAL_AMOUNT_DEPOSITS_PERIOD
        merchant_scope_limit.save()

        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("100"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_scope_limit.merchant
            ),
            amount=Decimal("30"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.SUCCESS
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("30.01"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Total deposit amount per period": "Total successful deposits amount 130.00 "
            "with current transaction amount 30.01 is greater than limit 150.00 for period 1h",
            "scope": "merchant",
        }

    def test_total_amount_withdrawals_period(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        merchant_scope_limit.limit_type = LimitType.TOTAL_AMOUNT_WITHDRAWALS_PERIOD
        merchant_scope_limit.save()

        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("100"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_scope_limit.merchant
            ),
            amount=Decimal("30"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.SUCCESS
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("30.01"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Total withdrawal amount per period": "Total successful withdrawals amount 130.00 "
            "with current transaction amount 30.01 is greater than limit 150.00 for period 1h",
            "scope": "merchant",
        }

    def test_max_withdrawal_to_deposit_ratio(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        merchant_scope_limit.limit_type = LimitType.MAX_WITHDRAWAL_TO_DEPOSIT_RATIO
        merchant_scope_limit.save()

        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("50"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_scope_limit.merchant
            ),
            amount=Decimal("50"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("50"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.SUCCESS
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("50"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Maximum withdrawal-to-deposit ratio per period": "Withdrawals to deposits ratio 50.00 is greater than limit 49.99",
            "scope": "merchant",
        }

    def test_multiple_limits(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        first_merchant_limit = merchant_scope_limit
        first_merchant_limit.limit_type = LimitType.MAX_AMOUNT_SINGLE_OPERATION
        first_merchant_limit.save()

        second_merchant_limit = MerchantLimitFactory.create(
            wallet=first_merchant_limit.wallet,
            merchant=first_merchant_limit.merchant,
        )
        second_merchant_limit.limit_type = LimitType.TOTAL_AMOUNT_DEPOSITS_PERIOD
        second_merchant_limit.save()

        assert first_merchant_limit.merchant.wallet_set.first()  # type: ignore
        payment_transaction = PaymentTransactionFactory.create(
            wallet=first_merchant_limit.merchant.wallet_set.first().currencywallet_set.first(),  # type: ignore
            amount=Decimal("2281488"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alerts = LimitAlert.objects.all().order_by("id")
        assert len(alerts) == 2
        assert first_merchant_limit in [alert.merchant_limit for alert in alerts]
        assert second_merchant_limit in [alert.merchant_limit for alert in alerts]
        assert payment_transaction in [alert.transaction for alert in alerts]
        assert {
            "Maximum amount for a single operation": "Transaction amount 2281488 is greater than limit 100.00",
            "scope": "merchant",
        } in [alert.extra for alert in alerts]
        assert {
            "Total deposit amount per period": "Total successful deposits amount 0 "
            "with current transaction amount 2281488 is greater than limit 150.00 for period 1h",
            "scope": "merchant",
        } in [alert.extra for alert in alerts]

    def test_in_celery_task(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        wallet: Wallet = merchant_scope_limit.merchant.wallet_set.first().currencywallet_set.first()  # type: ignore
        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )
        process_transaction.apply(kwargs={"transaction_id": payment_transaction.id})

        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.FAILED
        assert LimitAlert.objects.exists()
        decline_log = PaymentTransactionEventLog.objects.get(
            event_type=const.EventType.DECLINED_BY_LIMIT
        )
        assert decline_log.extra == {
            "0": {
                "Minimum amount for a single operation": "Transaction amount 9.99 is less than limit 10.00",
                "scope": "merchant",
            },
        }

        merchant_scope_limit.decline_on_exceed = False
        merchant_scope_limit.save()

        # Limit doesn't decline transaction, but creates alert
        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet,
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )
        controller = get_payment_system_controller(payment_transaction.system)
        with mock.patch.object(controller, "run_deposit") as run_deposit_mock:
            process_transaction.apply(kwargs={"transaction_id": payment_transaction.id})
            assert run_deposit_mock.call_count == 1

        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        assert LimitAlert.objects.count() == 2
        assert (
            PaymentTransactionEventLog.objects.filter(
                event_type=const.EventType.DECLINED_BY_LIMIT
            ).count()
            == 1
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestMerchantWalletScopeLimits:
    def test_clean_validation(
        self,
        merchant,
        merchant_scope_limit: MerchantLimit,
    ):
        with pytest.raises(ValidationError, match=".*already exists.*"):
            duplicate_limit = MerchantLimitFactory.create(
                limit_type=merchant_scope_limit.limit_type,
                period=merchant_scope_limit.period,
                wallet=merchant_scope_limit.wallet,
                merchant=merchant_scope_limit.merchant,
                scope=merchant_scope_limit.scope,
            )
            duplicate_limit.clean()

        with pytest.raises(ValidationError, match=".*must be set.*"):
            limit_without_required_params = MerchantLimitFactory.create(
                max_operations=None,
                max_overall_decline_percent=None,
                max_withdrawal_decline_percent=None,
                max_deposit_decline_percent=None,
                min_amount=None,
                max_amount=None,
                total_amount=None,
                max_ratio=None,
                burst_minutes=None,
            )
            limit_without_required_params.clean()

        with pytest.raises(ValidationError, match=".*Merchant is required*"):
            limit_with_merchant_scope = MerchantLimitFactory.create(
                merchant=None,
                scope=MerchantLimitScope.MERCHANT,
            )
            limit_with_merchant_scope.clean()

        with pytest.raises(ValidationError, match=".*Wallet is required*"):
            limit_with_wallet_scope = MerchantLimitFactory.create(
                wallet=None,
                scope=MerchantLimitScope.WALLET,
            )
            limit_with_wallet_scope.clean()

        with pytest.raises(ValidationError, match=".*Max ratio is required*"):
            limit_with_ratio = MerchantLimitFactory.create(
                limit_type=LimitType.MAX_WITHDRAWAL_TO_DEPOSIT_RATIO,
                max_ratio=None,
            )
            limit_with_ratio.clean()

        with pytest.raises(
            ValidationError, match="Wallet is required for wallet scope"
        ):
            wallet_limit_with_burst = MerchantLimitFactory.create(
                wallet=merchant_scope_limit.wallet,
                scope=MerchantLimitScope.WALLET,
                limit_type=LimitType.MAX_OPERATIONS_BURST,
            )
            wallet_limit_with_burst.clean()

        with pytest.raises(
            ValidationError,
            match=".*Burst minutes are required for max operations burst limit*",
        ):
            limit_without_burst_minutes = MerchantLimitFactory.create(
                merchant=merchant,
                scope=MerchantLimitScope.MERCHANT,
                limit_type=LimitType.MAX_OPERATIONS_BURST,
                burst_minutes=None,
            )
            limit_without_burst_minutes.clean()

        with pytest.raises(
            ValidationError,
            match=".*Max operations are required for max operations burst limit*",
        ):
            limit_without_max_operations = MerchantLimitFactory.create(
                merchant=merchant,
                scope=MerchantLimitScope.MERCHANT,
                limit_type=LimitType.MAX_OPERATIONS_BURST,
                max_operations=None,
            )
            limit_without_max_operations.clean()

    def test_min_operation_amount(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        assert merchant_wallet_scope_limit.wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit
        assert alert.extra == {
            "Minimum amount for a single operation": "Transaction amount 9.99 is less than limit 10.00",
            "scope": "wallet",
        }

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            status=const.TransactionStatus.PENDING,
        )
        is_declined, _ = limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert not is_declined

    def test_max_operation_amount(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = LimitType.MAX_AMOUNT_SINGLE_OPERATION
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("100.01"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit
        assert alert.extra == {
            "Maximum amount for a single operation": "Transaction amount 100.01 is greater than limit 100.00",
            "scope": "wallet",
        }

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )
        is_declined, _ = limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert not is_declined

    def test_max_successful_deposits(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = LimitType.MAX_SUCCESSFUL_DEPOSITS
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_wallet_scope_limit.wallet.merchant
            ),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        payment_transaction.status = const.TransactionStatus.SUCCESS
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit
        assert alert.extra == {
            "Maximum number of successful deposits per period": "Number of successful deposits 3 has exceeded limit 3",
            "scope": "wallet",
        }

    def test_max_overall_decline_percent(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = LimitType.MAX_OVERALL_DECLINE_PERCENT
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )

        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )

        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_wallet_scope_limit.wallet.merchant
            ),
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        is_declined, _ = limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert not is_declined
        payment_transaction.status = const.TransactionStatus.FAILED
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit
        assert alert.extra == {
            "Maximum decline percentage per period": "Failed transactions percent 33.33 is greater than limit 33.32",
            "scope": "wallet",
        }

    def test_max_withdrawal_decline_percent(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = (
            LimitType.MAX_WITHDRAWAL_DECLINE_PERCENT
        )
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )

        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_wallet_scope_limit.wallet.merchant
            ),
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )
        is_declined, _ = limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert not is_declined
        payment_transaction.status = const.TransactionStatus.FAILED
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit
        assert alert.extra == {
            "Maximum withdrawal decline percentage per period": "Failed withdrawals percent 33.33 is greater than limit 33.32",
            "scope": "wallet",
        }

    def test_max_deposit_decline_percent(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = LimitType.MAX_DEPOSIT_DECLINE_PERCENT
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_wallet_scope_limit.wallet.merchant
            ),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.FAILED,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        is_declined, _ = limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert not is_declined
        payment_transaction.status = const.TransactionStatus.FAILED
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit
        assert alert.extra == {
            "Maximum deposit decline percentage per period": "Failed deposits percent 40.00 is greater than limit 39.99",
            "scope": "wallet",
        }

    def test_total_amount_deposits_period(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = LimitType.TOTAL_AMOUNT_DEPOSITS_PERIOD
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("100"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_wallet_scope_limit.wallet.merchant
            ),
            amount=Decimal("100"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("30"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.SUCCESS
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("30.01"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit
        assert alert.extra == {
            "Total deposit amount per period": "Total successful deposits amount 130.00 "
            "with current transaction amount 30.01 is greater than limit 150.00 for period 1h",
            "scope": "wallet",
        }

    def test_total_amount_withdrawals_period(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = (
            LimitType.TOTAL_AMOUNT_WITHDRAWALS_PERIOD
        )
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("100"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_wallet_scope_limit.wallet.merchant
            ),
            amount=Decimal("100"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("30"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.SUCCESS
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("30.01"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit
        assert alert.extra == {
            "Total withdrawal amount per period": "Total successful withdrawals amount 130.00 "
            "with current transaction amount 30.01 is greater than limit 150.00 for period 1h",
            "scope": "wallet",
        }

    def test_max_withdrawal_to_deposit_ratio(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = (
            LimitType.MAX_WITHDRAWAL_TO_DEPOSIT_RATIO
        )
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("50"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("50"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        PaymentTransactionFactory.create(
            wallet=create_currency_wallet_from_second_wallet(
                merchant_wallet_scope_limit.wallet.merchant
            ),
            amount=Decimal("50"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("50"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.SUCCESS
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("50"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit
        assert alert.extra == {
            "Maximum withdrawal-to-deposit ratio per period": "Withdrawals to deposits ratio 50.00 is greater than limit 49.99",
            "scope": "wallet",
        }

    def test_max_operations_burst(
        self,
        merchant_scope_limit: MerchantLimit,
    ):
        merchant_scope_limit.limit_type = LimitType.MAX_OPERATIONS_BURST
        merchant_scope_limit.max_operations = 1
        merchant_scope_limit.burst_minutes = 10
        merchant_scope_limit.save()

        assert merchant_scope_limit.merchant
        wallet = merchant_scope_limit.merchant.wallet_set.first()
        assert wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet.currencywallet_set.first(),
            amount=Decimal("50"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        payment_transaction.created_at = payment_transaction.created_at - timedelta(
            minutes=10, seconds=1
        )
        payment_transaction.save()

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet.currencywallet_set.first(),
            amount=Decimal("50"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )
        limits._process_transaction_limits(payment_transaction)
        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        payment_transaction.status = const.TransactionStatus.SUCCESS
        payment_transaction.save()
        assert LimitAlert.objects.count() == 0

        payment_transaction = PaymentTransactionFactory.create(
            wallet=wallet.currencywallet_set.first(),
            amount=Decimal("50"),
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_scope_limit
        assert alert.extra == {
            "Maximum number of any operations in a short period": "Operations count 2 is greater than limit 1 for period 10 minutes",
            "scope": "merchant",
        }

    def test_multiple_limits(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        first_merchant_limit = merchant_wallet_scope_limit
        first_merchant_limit.limit_type = LimitType.MAX_AMOUNT_SINGLE_OPERATION
        first_merchant_limit.save()

        second_merchant_limit = MerchantLimitFactory.create(
            wallet=first_merchant_limit.wallet,
            merchant=first_merchant_limit.merchant,
        )
        second_merchant_limit.limit_type = LimitType.TOTAL_AMOUNT_DEPOSITS_PERIOD
        second_merchant_limit.scope = MerchantLimitScope.WALLET
        second_merchant_limit.save()

        assert first_merchant_limit.wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=first_merchant_limit.wallet.currencywallet_set.first(),
            amount=Decimal("2281488"),
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alerts = LimitAlert.objects.all()
        assert len(alerts) == 2
        assert alerts[0].transaction == payment_transaction
        assert alerts[0].merchant_limit == first_merchant_limit
        assert alerts[0].extra == {
            "Maximum amount for a single operation": "Transaction amount 2281488 is greater than limit 100.00",
            "scope": "wallet",
        }
        assert alerts[1].transaction == payment_transaction
        assert alerts[1].merchant_limit == second_merchant_limit
        assert alerts[1].extra == {
            "Total deposit amount per period": "Total successful deposits amount 0 "
            "with current transaction amount 2281488 is greater than limit 150.00 for period 1h",
            "scope": "wallet",
        }

    def test_in_celery_task(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        assert merchant_wallet_scope_limit.wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )
        process_transaction.apply(kwargs={"transaction_id": payment_transaction.id})

        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.FAILED
        assert LimitAlert.objects.exists()
        decline_log = PaymentTransactionEventLog.objects.get(
            event_type=const.EventType.DECLINED_BY_LIMIT
        )
        assert decline_log.extra == {
            "0": {
                "Minimum amount for a single operation": "Transaction amount 9.99 is less than limit 10.00",
                "scope": "wallet",
            },
        }

        merchant_wallet_scope_limit.decline_on_exceed = False
        merchant_wallet_scope_limit.save()

        # Limit doesn't decline transaction, but creates alert
        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("9.99"),
            status=const.TransactionStatus.PENDING,
        )
        controller = get_payment_system_controller(payment_transaction.system)
        with mock.patch.object(controller, "run_deposit") as run_deposit_mock:
            process_transaction.apply(kwargs={"transaction_id": payment_transaction.id})
            assert run_deposit_mock.call_count == 1

        payment_transaction.refresh_from_db()
        assert payment_transaction.status == const.TransactionStatus.PENDING
        assert LimitAlert.objects.count() == 2
        assert (
            PaymentTransactionEventLog.objects.filter(
                event_type=const.EventType.DECLINED_BY_LIMIT
            ).count()
            == 1
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestLimitPeriods:
    def test_one_hour_period(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = LimitType.MAX_SUCCESSFUL_DEPOSITS
        merchant_wallet_scope_limit.period = LimitPeriod.ONE_HOUR
        merchant_wallet_scope_limit.max_operations = 1
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        payment_transaction.created_at = timezone.now() - timedelta(hours=1, seconds=1)
        payment_transaction.save()

        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit

    def test_twenty_four_hours_period(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = LimitType.MAX_SUCCESSFUL_DEPOSITS
        merchant_wallet_scope_limit.period = LimitPeriod.TWENTY_FOUR_HOURS
        merchant_wallet_scope_limit.max_operations = 1
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        payment_transaction.created_at = timezone.now() - timedelta(hours=24, seconds=1)
        payment_transaction.save()

        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit

    def test_beginning_of_hour_period(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = LimitType.MAX_SUCCESSFUL_DEPOSITS
        merchant_wallet_scope_limit.period = LimitPeriod.BEGINNING_OF_HOUR
        merchant_wallet_scope_limit.max_operations = 1
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        payment_transaction.created_at = payment_transaction.created_at.replace(
            minute=0, second=0, microsecond=0
        ) - timedelta(seconds=1)
        payment_transaction.save()

        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit

    def test_beginning_of_day_period(
        self,
        merchant_wallet_scope_limit: MerchantLimit,
    ):
        merchant_wallet_scope_limit.limit_type = LimitType.MAX_SUCCESSFUL_DEPOSITS
        merchant_wallet_scope_limit.period = LimitPeriod.BEGINNING_OF_DAY
        merchant_wallet_scope_limit.max_operations = 1
        merchant_wallet_scope_limit.save()

        assert merchant_wallet_scope_limit.wallet
        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )
        payment_transaction.created_at = payment_transaction.created_at.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(seconds=1)
        payment_transaction.save()

        PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        payment_transaction = PaymentTransactionFactory.create(
            wallet=merchant_wallet_scope_limit.wallet.currencywallet_set.first(),
            amount=Decimal("10"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        is_declined, _ = limits._process_transaction_limits(payment_transaction)

        payment_transaction.refresh_from_db()

        assert is_declined
        alert = LimitAlert.objects.get()
        assert alert.transaction == payment_transaction
        assert alert.merchant_limit == merchant_wallet_scope_limit


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestAlerts:
    def test_clean_validation(
        self,
    ):
        created_alert: LimitAlert = LimitAlertFactory.create()
        with pytest.raises(
            ValidationError,
            match="Customer and merchant limits cannot be set at the same time",
        ):
            created_alert.clean()

        created_alert.customer_limit = None
        created_alert.extra = {}
        with pytest.raises(ValidationError, match="Extra data must be set"):
            created_alert.extra = None
            created_alert.clean()

            created_alert.extra = {}
            created_alert.extra = {}

        created_alert.extra = {}

        created_alert.merchant_limit = None
        with pytest.raises(
            ValidationError, match="Customer or merchant limit must be set"
        ):
            created_alert.clean()


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestFullFlow:
    def test_full_flow_multiple_limits_decline_transaction(
        self,
        customer: Customer,
        merchant: Merchant,
        wallet: Wallet,
    ):
        """Test full flow with multiple limits that should decline transaction."""
        # Create customer limit with decline enabled
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("100.00"),
            max_operation_amount=Decimal("500.00"),
            max_successful_operations=2,
            decline_on_exceed=True,
            is_critical=True,
        )

        # Create merchant min limit (will be filtered out by conflict resolution)
        MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("50.00"),
            decline_on_exceed=True,
            is_critical=False,
        )

        merchant_deposits_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            scope=MerchantLimitScope.WALLET,
            limit_type=LimitType.TOTAL_AMOUNT_DEPOSITS_PERIOD,
            total_amount=Decimal("301.00"),
            period=LimitPeriod.ONE_HOUR,
            decline_on_exceed=True,
            is_critical=True,
        )
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)

        # Create existing successful transactions to trigger max_successful_operations
        PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("150.00"),
            status=const.TransactionStatus.SUCCESS,
            wallet=currency_wallet,
        )
        PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("150.00"),
            status=const.TransactionStatus.SUCCESS,
            wallet=currency_wallet,
        )

        # Create transaction that violates min_operation_amount (below 100)
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            wallet=currency_wallet,
            amount=Decimal("75.00"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        controller = get_payment_system_controller(payment_transaction.system)

        with mock.patch.object(controller, "fail_transaction") as fail_transaction_mock:
            is_declined = limits.check_limits_and_maybe_decline_transaction(
                payment_transaction, controller
            )

        # Verify transaction was declined
        assert is_declined is True
        fail_transaction_mock.assert_called_once()

        # Verify fail_transaction was called with correct parameters
        call_args = fail_transaction_mock.call_args
        assert (
            call_args[1]["decline_code"] == const.TransactionDeclineCodes.LIMITS_DECLINE
        )

        # Verify alerts were created
        alerts = LimitAlert.objects.all().order_by("id")
        # Customer limit + merchant deposits limit (min limit filtered out by conflict resolution)
        assert len(alerts) == 2

        # Check customer limit alert
        customer_alert = alerts[0]
        assert customer_alert.customer_limit == customer_limit
        assert customer_alert.merchant_limit is None
        assert customer_alert.transaction == payment_transaction
        assert customer_alert.is_active is True
        assert customer_alert.is_critical is True
        assert (
            limit_const.VERBOSE_NAME_MIN_AMOUNT_SINGLE_OPERATION in customer_alert.extra
        )
        assert "max_successful_operations" in customer_alert.extra

        # Check merchant limit alert
        merchant_alert = alerts[1]
        assert merchant_alert.merchant_limit == merchant_deposits_limit
        assert merchant_alert.customer_limit is None
        assert merchant_alert.transaction == payment_transaction
        assert merchant_alert.is_active is True
        assert merchant_alert.is_critical is True
        assert "Total deposit amount per period" in merchant_alert.extra
        assert merchant_alert.extra["scope"] == "wallet"

        # Verify event log was created
        event_logs = PaymentTransactionEventLog.objects.filter(
            transaction_id=payment_transaction.id,
            event_type=const.EventType.DECLINED_BY_LIMIT,
        )
        assert event_logs.count() == 1

        event_log = event_logs.get()
        assert event_log
        assert event_log.description
        assert (
            f"Transaction {payment_transaction.id} declined by limits"
            in event_log.description
        )
        assert len(event_log.extra) == 2  # Two limits that decline

    def test_full_flow_multiple_limits_no_decline(
        self,
        customer,
        merchant,
        wallet,
    ):
        """Test full flow with multiple limits that create alerts but don't decline."""
        # Create customer limit without decline
        CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            max_operation_amount=Decimal("500.00"),
            decline_on_exceed=False,
            is_critical=False,
        )

        # Create merchant limit without decline
        MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_OVERALL_DECLINE_PERCENT,
            max_overall_decline_percent=Decimal("25.00"),
            decline_on_exceed=False,
            is_critical=True,
        )
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)

        # Create failed transactions to trigger decline percentage
        PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal("100.00"),
            status=const.TransactionStatus.FAILED,
        )
        PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal("100.00"),
            status=const.TransactionStatus.SUCCESS,
        )

        # Create transaction that violates max_operation_amount and decline percentage
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            wallet=currency_wallet,
            amount=Decimal("750.00"),
            status=const.TransactionStatus.PENDING,
        )

        controller = get_payment_system_controller(payment_transaction.system)

        with mock.patch.object(controller, "fail_transaction") as fail_transaction_mock:
            is_declined = limits.check_limits_and_maybe_decline_transaction(
                payment_transaction, controller
            )

        # Verify transaction was NOT declined
        assert is_declined is False
        fail_transaction_mock.assert_not_called()

        # Verify alerts were still created
        alerts = LimitAlert.objects.all()
        assert len(alerts) == 2

        # Verify no event log for decline was created
        event_logs = PaymentTransactionEventLog.objects.filter(
            transaction_id=payment_transaction.id,
            event_type=const.EventType.DECLINED_BY_LIMIT,
        )
        assert event_logs.count() == 0

    def test_full_flow_mixed_decline_settings(
        self,
        customer,
        merchant,
        wallet,
    ):
        """Test flow with mixed decline settings - some limits decline, others don't."""
        # Create customer limit with decline enabled
        CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("100.00"),
            decline_on_exceed=True,
            is_critical=True,
        )

        # Create merchant limit without decline
        MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=1,
            decline_on_exceed=False,
            is_critical=False,
        )
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)

        # Create existing deposit to trigger merchant limit
        PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal("50.00"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.SUCCESS,
        )

        # Create transaction that violates both limits
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            wallet=currency_wallet,
            amount=Decimal("75.00"),  # Below customer min of 100
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        controller = get_payment_system_controller(payment_transaction.system)

        with mock.patch.object(controller, "fail_transaction") as fail_transaction_mock:
            is_declined = limits.check_limits_and_maybe_decline_transaction(
                payment_transaction, controller
            )

        # Verify transaction was declined (because customer limit has decline=True)
        assert is_declined is True
        fail_transaction_mock.assert_called_once()

        # Verify both alerts were created
        alerts = LimitAlert.objects.all()
        assert len(alerts) == 2

        # Verify event log contains only the declining alert
        event_logs = PaymentTransactionEventLog.objects.filter(
            transaction_id=payment_transaction.id,
            event_type=const.EventType.DECLINED_BY_LIMIT,
        )
        assert event_logs.count() == 1

        event_log = event_logs.get()
        # Should only have one entry for the declining limit
        assert len(event_log.extra) == 1

    def test_full_flow_no_limits_triggered(
        self,
        customer,
        merchant,
        wallet,
    ):
        """Test flow when no limits are triggered."""
        # Create limits that won't be triggered
        CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("10.00"),
            max_operation_amount=Decimal("1000.00"),
            decline_on_exceed=True,
        )

        MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=10,
            decline_on_exceed=True,
        )
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        # Create transaction that doesn't violate any limits
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            wallet=currency_wallet,
            amount=Decimal("100.00"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        controller = get_payment_system_controller(payment_transaction.system)

        with mock.patch.object(controller, "fail_transaction") as fail_transaction_mock:
            is_declined = limits.check_limits_and_maybe_decline_transaction(
                payment_transaction, controller
            )

        # Verify transaction was NOT declined
        assert is_declined is False
        fail_transaction_mock.assert_not_called()

        # Verify no alerts were created
        assert LimitAlert.objects.count() == 0

        # Verify no event logs were created
        assert PaymentTransactionEventLog.objects.count() == 0

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack")
    def test_full_flow_slack_notifications(
        self,
        mock_notify_slack,
        customer,
        merchant,
        wallet,
    ):
        """Test that Slack notifications are sent for critical and regular alerts."""
        # Create critical customer limit
        CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("100.00"),
            decline_on_exceed=False,
            is_critical=True,
        )

        # Create non-critical merchant limit
        MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=0,  # Will trigger immediately
            decline_on_exceed=False,
            is_critical=False,
        )
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        # Create transaction that violates both limits
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            wallet=currency_wallet,
            amount=Decimal("75.00"),
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )

        controller = get_payment_system_controller(payment_transaction.system)

        limits.check_limits_and_maybe_decline_transaction(
            payment_transaction, controller
        )

        # Verify Slack notifications were called for both critical and regular alerts
        assert mock_notify_slack.apply_async.call_count == 2

        # Check the calls
        calls = mock_notify_slack.apply_async.call_args_list

        # Find critical and regular notifications
        critical_call = None
        regular_call = None

        for call in calls:
            kwargs = call[1]["kwargs"]
            if kwargs["channel"] == limit_const.SLACK_CHANNEL_NAME_CRITICAL_LIMITS:
                critical_call = call
            elif kwargs["channel"] == limit_const.SLACK_CHANNEL_NAME_REGULAR_LIMITS:
                regular_call = call

        assert critical_call is not None
        assert regular_call is not None
        assert "message" in critical_call[1]["kwargs"]
        assert "message" in regular_call[1]["kwargs"]


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestRiskAndBusinessLimitCategories:
    def test_business_customer_limit_always_checked(self, customer):
        business_limit = CustomerLimitFactory.create(
            customer=customer,
            category=LimitCategory.BUSINESS,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=1,
            decline_on_exceed=True,
        )

        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        should_check = limits._should_check_customer_limit(
            business_limit,
            payment_transaction,
            is_customer_in_gray_list=False,
        )
        assert should_check is True

    def test_risk_customer_limit_checked_when_feature_enabled(self, customer):
        risk_limit = CustomerLimitFactory.create(
            customer=customer,
            category=LimitCategory.RISK,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=1,
            decline_on_exceed=True,
        )

        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        customer.risk_control = True
        customer.save()

        with mock.patch(
            "rozert_pay.limits.services.limits.is_customer_in_list",
            return_value=True,
        ):
            should_check = limits._should_check_customer_limit(
                risk_limit,
                payment_transaction,
                is_customer_in_gray_list=True,
            )
            assert should_check is True

    def test_risk_customer_limit_not_checked_when_risk_control_is_disabled(
        self, customer
    ):
        risk_limit = CustomerLimitFactory.create(
            customer=customer,
            category=LimitCategory.RISK,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=1,
            decline_on_exceed=True,
        )
        customer.risk_control = False
        customer.save()

        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        with mock.patch(
            "rozert_pay.limits.services.limits.is_customer_in_list",
            return_value=True,
        ):
            should_check = limits._should_check_customer_limit(
                risk_limit,
                payment_transaction,
                is_customer_in_gray_list=True,
            )
            assert should_check is False

    def test_risk_customer_limit_not_checked_when_not_in_gray_list(self, customer):
        risk_limit = CustomerLimitFactory.create(
            customer=customer,
            category=LimitCategory.RISK,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=1,
            decline_on_exceed=True,
        )

        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        customer.risk_control = True
        customer.save()

        with mock.patch(
            "rozert_pay.limits.services.limits.is_customer_in_list",
            return_value=False,
        ):
            should_check = limits._should_check_customer_limit(
                risk_limit,
                payment_transaction,
                is_customer_in_gray_list=False,
            )
            assert should_check is False

    def test_risk_customer_limit_not_checked_when_risk_control_disabled(
        self,
        customer,
    ):
        risk_limit = CustomerLimitFactory.create(
            customer=customer,
            category=LimitCategory.RISK,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=1,
            decline_on_exceed=True,
        )

        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        customer.risk_control = False
        customer.save()

        with mock.patch(
            "rozert_pay.limits.services.limits.is_customer_in_list",
            return_value=True,
        ):
            should_check = limits._should_check_customer_limit(
                risk_limit, payment_transaction
            )
            assert should_check is False

    def test_business_merchant_limit_always_checked(self, merchant, wallet):
        business_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            category=LimitCategory.BUSINESS,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=1,
            decline_on_exceed=True,
        )

        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        payment_transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        should_check = limits._should_check_merchant_limit(
            business_limit,
            payment_transaction,
        )
        assert should_check is True

    def test_risk_merchant_limit_checked_when_feature_enabled_wallet_scope(
        self,
        merchant,
        wallet,
    ):
        wallet.risk_control = True
        wallet.save()

        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=1,
            decline_on_exceed=True,
        )

        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        payment_transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        should_check = limits._should_check_merchant_limit(
            risk_limit,
            payment_transaction,
        )
        assert should_check is True

    def test_risk_merchant_limit_checked_when_feature_enabled_merchant_scope(
        self,
        merchant,
        wallet,
    ):
        merchant.risk_control = True
        merchant.save()

        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=1,
            decline_on_exceed=True,
        )

        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        payment_transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        should_check = limits._should_check_merchant_limit(
            risk_limit,
            payment_transaction,
        )
        assert should_check is True

    def test_risk_merchant_limit_not_checked_when_feature_disabled(
        self,
        merchant,
        wallet,
    ):
        merchant.risk_control = False
        merchant.save()

        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=1,
            decline_on_exceed=True,
        )

        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        payment_transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        should_check = limits._should_check_merchant_limit(
            risk_limit,
            payment_transaction,
        )
        assert should_check is False

    def test_risk_merchant_limit_not_checked_when_risk_control_disabled_wallet(
        self,
        merchant,
        wallet,
    ):
        wallet.risk_control = False
        wallet.save()

        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=1,
            decline_on_exceed=True,
        )

        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        payment_transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        should_check = limits._should_check_merchant_limit(
            risk_limit,
            payment_transaction,
        )
        assert should_check is False

    def test_risk_merchant_limit_not_checked_when_risk_control_disabled_merchant(
        self,
        merchant,
        wallet,
    ):
        merchant.risk_control = False
        merchant.save()

        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=1,
            decline_on_exceed=True,
        )

        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        payment_transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal("100"),
            status=const.TransactionStatus.PENDING,
        )

        should_check = limits._should_check_merchant_limit(
            risk_limit,
            payment_transaction,
        )
        assert should_check is False

    def test_mixed_risk_and_business_limits_processed_correctly(
        self,
        customer,
        merchant,
        wallet,
    ):
        customer.risk_control = True
        customer.save()

        risk_customer_limit = CustomerLimitFactory.create(
            customer=customer,
            category=LimitCategory.RISK,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("50"),
            decline_on_exceed=True,
        )

        CustomerLimitFactory.create(
            customer=customer,
            category=LimitCategory.BUSINESS,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=1,
            decline_on_exceed=True,
        )

        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        currency_wallet.wallet.risk_control = True
        currency_wallet.wallet.save()
        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            wallet=currency_wallet,
            amount=Decimal("10"),
            status=const.TransactionStatus.PENDING,
        )

        with mock.patch(
            "rozert_pay.limits.services.limits.is_customer_in_list",
            return_value=True,
        ):
            is_declined, alerts = limits._process_transaction_limits(
                payment_transaction,
            )

        assert is_declined is True
        assert len(alerts) == 1
        assert alerts[0].customer_limit == risk_customer_limit


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestResolveLimitConflicts:
    def test_customer_limits_override_merchant_operation_limits(
        self,
        customer,
        merchant,
    ):
        """Test that customer operation limits override conflicting merchant limits."""
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("20.00"),
            max_operation_amount=Decimal("500.00"),
        )

        merchant_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )

        merchant_max_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )

        merchant_other_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=5,
        )

        limits_list: list[CustomerLimit | MerchantLimit] = [
            customer_limit,
            merchant_min_limit,
            merchant_max_limit,
            merchant_other_limit,
        ]
        resolved_limits = limits._resolve_limit_conflicts(limits_list)

        # Should keep customer limit and non-conflicting merchant limit
        assert len(resolved_limits) == 2
        assert customer_limit in resolved_limits
        assert merchant_other_limit in resolved_limits

        # Should remove conflicting merchant limits
        assert merchant_min_limit not in resolved_limits
        assert merchant_max_limit not in resolved_limits


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestLimitNotificationAndGroups:
    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack")
    def test_notification_groups_are_set_on_alert(self, mock_notify_slack, customer):
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("10.00"),
            decline_on_exceed=False,
        )
        group1 = Group.objects.create(name="Support Team")
        group2 = Group.objects.create(name="Finance Team")

        customer_limit.notification_groups.add(group1, group2)

        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("5.00"),
            status=const.TransactionStatus.PENDING,
        )

        limits._process_transaction_limits(payment_transaction)

        alert = LimitAlert.objects.get()
        assert alert.customer_limit == customer_limit
        assert alert.notification_groups.count() == 2
        assert group1 in alert.notification_groups.all()
        assert group2 in alert.notification_groups.all()

        mock_notify_slack.apply_async.assert_called_once()

    @mock.patch("rozert_pay.limits.services.limits.notify_in_slack")
    def test_slack_channel_override_is_used(self, mock_notify_slack, customer):
        custom_channel = "#test-channel-override"
        CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("10.00"),
            decline_on_exceed=False,
            slack_channel_override=custom_channel,
        )

        payment_transaction = PaymentTransactionFactory.create(
            customer=customer,
            amount=Decimal("5.00"),
            status=const.TransactionStatus.PENDING,
        )

        limits._process_transaction_limits(payment_transaction)

        mock_notify_slack.apply_async.assert_called_once()
        call_kwargs = mock_notify_slack.apply_async.call_args[1]["kwargs"]
        assert call_kwargs["channel"] == custom_channel

    @mock.patch("rozert_pay.limits.tasks.notify_in_slack")
    def test_notify_about_alerts_with_no_channel_alerts_does_not_call_slack(
        self, mock_notify_slack_task
    ):
        # Call _notify_about_alerts with an empty list of alerts.
        # This will result in alerts_by_channel being empty, and the loop
        # over alerts_by_channel.items() will not run.
        limits._notify_about_alerts([])

        mock_notify_slack_task.apply_async.assert_not_called()
