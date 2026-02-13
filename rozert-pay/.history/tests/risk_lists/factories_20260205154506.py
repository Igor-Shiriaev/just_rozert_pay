import factory
from factory.django import DjangoModelFactory
from rozert_pay.risk_lists.const import (
    ListType,
    OperationType,
    Scope,
    ValidFor,
)
from rozert_pay.risk_lists.models import (
    BlackListEntry,
    GrayListEntry,
    MerchantBlackListEntry,
    RiskListEntry,
    WhiteListEntry,
)
from tests.factories import CustomerFactory, MerchantFactory


class RiskListEntryFactory(DjangoModelFactory[RiskListEntry]):
    class Meta:
        model = RiskListEntry

    list_type = ListType.GRAY
    scope = Scope.GLOBAL
    operation_type = OperationType.ALL
    valid_for = ValidFor.PERMANENT
    reason = "Test reason"
    customer = factory.SubFactory(CustomerFactory)
    email: str | None = None
    phone: str | None = None
    ip: str | None = None
    customer_name: str | None = None
    masked_pan: str | None = None
    customer_wallet_id: str | None = None
    provider_code: str | None = None


class WhiteListEntryFactory(RiskListEntryFactory):
    class Meta:
        model = WhiteListEntry

    list_type = ListType.WHITE
    valid_for = ValidFor.H24
    scope = Scope.MERCHANT
    merchant = factory.SubFactory(MerchantFactory)


class BlackListEntryFactory(RiskListEntryFactory):
    class Meta:
        model = BlackListEntry

    list_type = ListType.BLACK
    valid_for = ValidFor.PERMANENT


class GrayListEntryFactory(RiskListEntryFactory):
    class Meta:
        model = GrayListEntry

    list_type = ListType.GRAY
    valid_for = ValidFor.PERMANENT


class MerchantBlackListEntryFactory(RiskListEntryFactory):
    class Meta:
        model = MerchantBlackListEntry

    list_type = ListType.MERCHANT_BLACK
    valid_for = ValidFor.PERMANENT
    scope = Scope.MERCHANT
    merchant = factory.SubFactory(MerchantFactory)
