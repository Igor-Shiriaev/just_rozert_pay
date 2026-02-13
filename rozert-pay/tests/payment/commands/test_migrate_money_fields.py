from decimal import Decimal

import pytest
from django.core.management import call_command
from rozert_pay.balances.models import BalanceTransaction
from rozert_pay.payment.models import PaymentTransaction
from tests.factories import BalanceTransactionFactory, PaymentTransactionFactory


@pytest.mark.django_db
class TestMigrateMoneyFieldsCommand:
    def test_migrates_payment_transaction_fields(self) -> None:
        transaction = PaymentTransactionFactory.create(
            amount=Decimal("12.34"),
            currency="EUR",
        )
        PaymentTransaction.objects.filter(id=transaction.id).update(
            amount2=None,
            currency2=None,
        )

        call_command("migrate_money_fields", payment_transaction=True)

        transaction.refresh_from_db()
        assert transaction.amount2 == transaction.amount
        assert transaction.currency2 == transaction.currency

    def test_migrates_balance_transaction_fields(self) -> None:
        balance_transaction = BalanceTransactionFactory.create()
        BalanceTransaction.objects.filter(id=balance_transaction.id).update(
            amount2=None,
            operational_before2=None,
            operational_after2=None,
            frozen_before2=None,
            frozen_after2=None,
            pending_before2=None,
            pending_after2=None,
        )

        call_command("migrate_money_fields", balance_transaction=True)

        balance_transaction.refresh_from_db()
        assert balance_transaction.amount2 == balance_transaction.amount
        assert (
            balance_transaction.operational_before2
            == balance_transaction.operational_before
        )
        assert (
            balance_transaction.operational_after2
            == balance_transaction.operational_after
        )
        assert balance_transaction.frozen_before2 == balance_transaction.frozen_before
        assert balance_transaction.frozen_after2 == balance_transaction.frozen_after
        assert balance_transaction.pending_before2 == balance_transaction.pending_before
        assert balance_transaction.pending_after2 == balance_transaction.pending_after

    def test_does_not_override_existing_values(self) -> None:
        transaction = PaymentTransactionFactory.create(
            amount=Decimal("22.22"),
            currency="USD",
        )
        PaymentTransaction.objects.filter(id=transaction.id).update(
            amount2=Decimal("99.99"),
            currency2="GBP",
        )

        call_command("migrate_money_fields", payment_transaction=True)

        transaction.refresh_from_db()
        assert transaction.amount2 == Decimal("99.99")
        assert transaction.currency2 == "GBP"
