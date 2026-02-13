from typing import Any

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory
from rozert_pay.account.models import User
from rozert_pay.common import const
from rozert_pay.common.const import CallbackStatus, TransactionType
from rozert_pay.limits.const import LimitPeriod
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.limit_alert import LimitAlert
from rozert_pay.limits.models.merchant_limits import (
    LimitType,
    MerchantLimit,
    MerchantLimitScope,
)
from rozert_pay.payment.entities import PaymentClientWithdrawResponse, UserData
from rozert_pay.payment.models import (
    CurrencyWallet,
    Customer,
    DepositAccount,
    IncomingCallback,
    Merchant,
    MerchantGroup,
    OutcomingCallback,
    PaymentSystem,
    PaymentTransaction,
    PaymentTransactionEventLog,
    Wallet,
)
from rozert_pay.payment.services import db_services  # noqa
from rozert_pay.payment.services.transaction_status_validation import (
    CleanRemoteTransactionStatus,
)


class UserFactory(DjangoModelFactory[User]):
    email = factory.Faker("email")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        result = super()._create(model_class, *args, **kwargs)
        result.set_password("123")
        result.save()
        return result

    class Meta:
        model = "account.User"


class MerchantGroupFactory(DjangoModelFactory[MerchantGroup]):
    name = factory.Faker("company")
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = MerchantGroup


class MerchantFactory(DjangoModelFactory[Merchant]):
    name = factory.Faker("company")
    merchant_group = factory.SubFactory(MerchantGroupFactory)
    secret_key = factory.Faker("uuid4")

    class Meta:
        model = Merchant


class PaymentSystemFactory(DjangoModelFactory[PaymentSystem]):
    name = factory.Faker("company")
    is_active = True
    type = const.PaymentSystemType.PAYCASH

    class Meta:
        model = PaymentSystem


class WalletFactory(DjangoModelFactory[Wallet]):
    merchant = factory.SubFactory(MerchantFactory)
    system = factory.SubFactory(PaymentSystemFactory)

    class Meta:
        model = Wallet


class CurrencyWalletFactory(DjangoModelFactory[CurrencyWallet]):
    wallet = factory.SubFactory(WalletFactory)
    currency = "USD"
    balance = 100

    class Meta:
        model = CurrencyWallet


class PaymentTransactionFactory(DjangoModelFactory["db_services.LockedTransaction"]):
    wallet = factory.SubFactory(CurrencyWalletFactory)
    amount = 100
    type = TransactionType.DEPOSIT
    currency = "USD"
    callback_url = "http://callback"
    redirect_url = "http://redirect"

    class Meta:
        model = PaymentTransaction


class OutcomingCallbackFactory(DjangoModelFactory[OutcomingCallback]):
    transaction = factory.SubFactory(PaymentTransactionFactory)
    callback_type = "OUTCOMING"
    target = factory.Faker("url")
    body = factory.Faker("sentence")
    status = CallbackStatus.SUCCESS
    error = None
    max_attempts = 5
    current_attempt = 1

    @factory.lazy_attribute
    def last_attempt_at(self):
        return timezone.now()

    class Meta:
        model = OutcomingCallback


class DepositAccountFactory(DjangoModelFactory[DepositAccount]):
    wallet = factory.SubFactory(WalletFactory)
    customer_id = factory.Faker("uuid4")
    unique_account_identifier = factory.Faker("uuid4")
    extra = factory.DictFactory()

    class Meta:
        model = DepositAccount


class UserDataFactory(factory.Factory[UserData]):
    class Meta:
        model = UserData

    email = "test@test.com"
    phone = "+1234567890"
    first_name = "John"
    last_name = "Doe"
    post_code = "123456"
    city = "Taraz"
    country = "Kazakhstan"
    state = "Zhambyl"
    address = "Lenina 1"
    language = "en"


class RemoteTransactionStatusFactory(factory.Factory[CleanRemoteTransactionStatus]):
    class Meta:
        model = CleanRemoteTransactionStatus

    operation_status = const.TransactionStatus.PENDING
    raw_data: dict[str, Any] = {}
    id_in_payment_system = "123"


class PaymentClientWithdrawResponseFactory(
    factory.Factory[PaymentClientWithdrawResponse]
):
    class Meta:
        model = PaymentClientWithdrawResponse

    status = const.TransactionStatus.PENDING
    id_in_payment_system = "123"
    raw_response: dict[str, Any] = {}


class CustomerFactory(DjangoModelFactory[Customer]):
    uuid = factory.Faker("uuid4")
    external_id = factory.Faker("uuid4")
    email = factory.Faker("email")
    phone = factory.Faker("phone_number")
    language = factory.Faker("language_code")
    extra = factory.DictFactory()

    class Meta:
        model = Customer


class CustomerLimitFactory(DjangoModelFactory[CustomerLimit]):
    active = True
    customer = factory.SubFactory(CustomerFactory)
    description = "Test customer limit"
    period = LimitPeriod.ONE_HOUR
    max_successful_operations = 3
    max_failed_operations = 2
    min_operation_amount = 100
    max_operation_amount = 1000
    total_successful_amount = 2000
    decline_on_exceed = True
    is_critical = True
    category = LimitCategory.BUSINESS

    class Meta:
        model = CustomerLimit


class MerchantLimitFactory(DjangoModelFactory[MerchantLimit]):
    active = True
    description = ""
    scope = MerchantLimitScope.MERCHANT
    merchant = factory.SubFactory(MerchantFactory)
    wallet = None
    limit_type = LimitType.MIN_AMOUNT_SINGLE_OPERATION
    period = LimitPeriod.ONE_HOUR
    max_operations = 3
    max_overall_decline_percent = 33.32
    max_withdrawal_decline_percent = 33.32
    max_deposit_decline_percent = 39.99
    min_amount = 10
    max_amount = 100
    total_amount = 150
    max_ratio = 49.99
    burst_minutes = 10
    decline_on_exceed = True
    is_critical = True

    class Meta:
        model = MerchantLimit


class LimitAlertFactory(DjangoModelFactory[LimitAlert]):
    customer_limit = factory.SubFactory(CustomerLimitFactory)
    merchant_limit = factory.SubFactory(MerchantLimitFactory)
    transaction = factory.SubFactory(PaymentTransactionFactory)
    extra = factory.DictFactory()

    class Meta:
        model = LimitAlert


class IncomingCallbackFactory(DjangoModelFactory[IncomingCallback]):
    system = factory.SubFactory(PaymentSystemFactory)
    transaction = factory.SubFactory(PaymentTransactionFactory)
    body = factory.Faker("text")
    headers = factory.DictFactory()
    get_params = factory.DictFactory()
    ip = factory.Faker("ipv4")
    status = CallbackStatus.PENDING
    error_type = None
    error = None
    traceback = None
    remote_transaction_status = factory.DictFactory()

    @factory.lazy_attribute
    def created_at(self):
        return timezone.now()

    @factory.lazy_attribute
    def updated_at(self):
        return timezone.now()

    class Meta:
        model = IncomingCallback


class PaymentTransactionEventLogFactory(DjangoModelFactory[PaymentTransactionEventLog]):
    transaction = factory.SubFactory(PaymentTransactionFactory)
    incoming_callback = factory.SubFactory(
        IncomingCallbackFactory,
        transaction=factory.SelfAttribute("..transaction"),  # type: ignore
    )
    event_type = const.EventType.INFO
    description = factory.Faker("sentence")
    extra = factory.DictFactory()
    request_id = factory.Faker("uuid4")

    @factory.lazy_attribute
    def created_at(self):
        return timezone.now()

    @factory.lazy_attribute
    def updated_at(self):
        return timezone.now()

    class Meta:
        model = "payment.PaymentTransactionEventLog"
