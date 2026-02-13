import pytest
from rozert_pay.common.const import EventType, TransactionExtraFields, TransactionType
from rozert_pay.payment.models import PaymentTransactionEventLog
from rozert_pay.risk_lists.const import Reason, Scope, ValidFor
from rozert_pay.risk_lists.models import BlackListEntry
from rozert_pay.risk_lists.services.manager import add_customer_to_blacklist_by_trx
from tests.factories import CustomerFactory, PaymentTransactionFactory
from tests.risk_lists.factories import BlackListEntryFactory


@pytest.mark.django_db
class TestAddCustomerToBlacklistByTrx:
    def test_successfully_adds_customer_to_blacklist(self) -> None:
        customer = CustomerFactory.create()
        trx = PaymentTransactionFactory.create(
            customer=customer,
            type=TransactionType.DEPOSIT,
            extra={},
        )

        add_customer_to_blacklist_by_trx(trx, Reason.CHARGEBACK)

        trx.refresh_from_db()
        assert trx.extra[TransactionExtraFields.IS_CUSTOMER_BLACKLISTED] is True

        blacklist_entry = BlackListEntry.objects.get(transaction=trx)
        assert blacklist_entry.customer == customer
        assert blacklist_entry.merchant == trx.wallet.wallet.merchant
        assert blacklist_entry.transaction == trx
        assert blacklist_entry.scope == Scope.MERCHANT
        assert blacklist_entry.valid_for == ValidFor.PERMANENT
        assert blacklist_entry.reason == Reason.CHARGEBACK
        assert blacklist_entry.added_by is None

        event_log = PaymentTransactionEventLog.objects.get(transaction=trx)
        assert event_log.event_type == EventType.INFO
        assert event_log.description == "Customer has been blacklisted"
        assert event_log.extra["customer_id"] == customer.id
        assert event_log.extra["merchant_id"] == trx.wallet.wallet.merchant.id
        assert event_log.extra["black_list_entry_id"] == blacklist_entry.id

    def test_raises_assertion_error_when_no_customer(self) -> None:
        trx = PaymentTransactionFactory.create(
            customer=None,
            type=TransactionType.DEPOSIT,
            extra={},
        )

        with pytest.raises(AssertionError):
            add_customer_to_blacklist_by_trx(trx, Reason.CHARGEBACK)

    def test_raises_assertion_error_when_not_deposit(self) -> None:
        customer = CustomerFactory.create()
        trx = PaymentTransactionFactory.create(
            customer=customer,
            type=TransactionType.WITHDRAWAL,
            extra={},
        )

        with pytest.raises(AssertionError):
            add_customer_to_blacklist_by_trx(trx, Reason.CHARGEBACK)

    def test_raises_assertion_error_when_already_blacklisted_flag_set(self) -> None:
        customer = CustomerFactory.create()
        trx = PaymentTransactionFactory.create(
            customer=customer,
            type=TransactionType.DEPOSIT,
            extra={TransactionExtraFields.IS_CUSTOMER_BLACKLISTED: True},
        )

        with pytest.raises(AssertionError):
            add_customer_to_blacklist_by_trx(trx, Reason.CHARGEBACK)

    def test_when_customer_already_blacklisted_does_not_duplicate_and_logs(
        self, dis
    ) -> None:
        customer = CustomerFactory.create()
        trx = PaymentTransactionFactory.create(
            customer=customer,
            type=TransactionType.DEPOSIT,
            extra={},
        )
        merchant = trx.wallet.wallet.merchant
        BlackListEntryFactory.create(
            customer=customer,
            merchant=merchant,
            scope=Scope.MERCHANT,
        )

        add_customer_to_blacklist_by_trx(trx, Reason.CHARGEBACK)

        trx.refresh_from_db()
        assert trx.extra[TransactionExtraFields.IS_CUSTOMER_BLACKLISTED] is True
        assert BlackListEntry.objects.filter(customer=customer).count() == 1

        event_log = PaymentTransactionEventLog.objects.get(transaction=trx)
        assert event_log.description == "Customer is already blacklisted"
        assert event_log.extra["black_list_entry_id"] is not None

    def test_handles_extra_with_existing_keys(self) -> None:
        customer = CustomerFactory.create()
        trx = PaymentTransactionFactory.create(
            customer=customer,
            type=TransactionType.DEPOSIT,
            extra={"some_other_key": "value"},
        )

        add_customer_to_blacklist_by_trx(trx, Reason.CHARGEBACK)

        trx.refresh_from_db()
        assert trx.extra[TransactionExtraFields.IS_CUSTOMER_BLACKLISTED] is True
        assert trx.extra["some_other_key"] == "value"
