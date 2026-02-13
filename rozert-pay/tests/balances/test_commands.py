from decimal import Decimal

import pytest
from django.core.management import call_command
from rozert_pay.balances.const import BalanceTransactionType as BalanceEventType
from rozert_pay.balances.models import BalanceTransaction
from rozert_pay.common.const import TransactionStatus, TransactionType
from tests.factories import (
    BalanceTransactionFactory,
    CurrencyWalletFactory,
    PaymentTransactionFactory,
)

pytestmark = pytest.mark.django_db


class TestBackfillBalancesCommand:
    """
    Tests the backfill_balances management command to ensure it's
    correct, idempotent, and safe.
    """

    def test_successful_deposit_creates_two_balance_transactions(self):
        """
        Business Logic: Verifies that a successful historic deposit
        correctly creates an OPERATION_CONFIRMED record AND its
        simulated SETTLEMENT_FROM_PROVIDER record.
        """
        wallet = CurrencyWalletFactory.create(operational_balance=0, pending_balance=0)
        trx = PaymentTransactionFactory.create(
            wallet=wallet,
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.SUCCESS,
            amount=Decimal("150.75"),
        )

        call_command("backfill_balances")

        assert BalanceTransaction.objects.count() == 2

        main_tx = BalanceTransaction.objects.get(
            type=BalanceEventType.OPERATION_CONFIRMED
        )
        settlement_tx = BalanceTransaction.objects.get(
            type=BalanceEventType.SETTLEMENT_FROM_PROVIDER
        )

        assert main_tx.payment_transaction == trx
        assert main_tx.amount == Decimal("150.75")
        assert settlement_tx.payment_transaction == trx
        assert settlement_tx.amount == Decimal("150.75")

        wallet.refresh_from_db()
        assert wallet.operational_balance == Decimal("150.75")
        assert wallet.pending_balance == Decimal("0.00")

    def test_successful_withdrawal_creates_two_balance_transactions(self):
        """
        Business Logic: Verifies a successful historic withdrawal
        creates two audit records: a request (freeze) and a
        confirmation (debit from frozen).
        """
        wallet = CurrencyWalletFactory.create(
            operational_balance=Decimal("1000.00"), frozen_balance=Decimal("0.00")
        )
        trx = PaymentTransactionFactory.create(
            wallet=wallet,
            type=TransactionType.WITHDRAWAL,
            status=TransactionStatus.SUCCESS,
            amount=Decimal("250.00"),
        )

        call_command("backfill_balances")

        assert BalanceTransaction.objects.count() == 2

        request_tx = BalanceTransaction.objects.get(
            type=BalanceEventType.SETTLEMENT_REQUEST
        )
        confirm_tx = BalanceTransaction.objects.get(
            type=BalanceEventType.SETTLEMENT_CONFIRMED
        )

        assert request_tx.payment_transaction == trx
        assert request_tx.amount == Decimal("250.00")

        assert confirm_tx.payment_transaction == trx
        assert confirm_tx.amount == Decimal("-250.00")

        wallet.refresh_from_db()
        assert wallet.operational_balance == Decimal("750.00")
        assert wallet.frozen_balance == Decimal("0.00")

    def test_failed_withdrawal_creates_two_balance_transactions(self):
        """
        Business Logic: A failed withdrawal implies funds were requested (frozen)
        and then released. This should result in TWO records:
        SETTLEMENT_REQUEST and SETTLEMENT_CANCEL.
        """
        wallet = CurrencyWalletFactory.create(
            operational_balance=Decimal("1000.00"), frozen_balance=Decimal("0.00")
        )
        trx = PaymentTransactionFactory.create(
            wallet=wallet,
            type=TransactionType.WITHDRAWAL,
            status=TransactionStatus.FAILED,
            amount=Decimal("300.00"),
        )

        call_command("backfill_balances")

        assert BalanceTransaction.objects.count() == 2

        request_tx = BalanceTransaction.objects.get(
            type=BalanceEventType.SETTLEMENT_REQUEST
        )
        cancel_tx = BalanceTransaction.objects.get(
            type=BalanceEventType.SETTLEMENT_CANCEL
        )

        assert request_tx.payment_transaction == trx
        assert request_tx.amount == Decimal("300.00")

        assert cancel_tx.type == BalanceEventType.SETTLEMENT_CANCEL
        assert cancel_tx.payment_transaction == trx
        assert cancel_tx.amount == Decimal("300.00")

        wallet.refresh_from_db()
        assert wallet.operational_balance == Decimal("1000.00")
        assert wallet.frozen_balance == Decimal("0.00")

    def test_failed_deposit_creates_no_balance_transactions(self):
        """
        Business Logic: A failed deposit had no impact on the balance,
        so no audit record should be created.
        """
        wallet = CurrencyWalletFactory.create(operational_balance=0)
        PaymentTransactionFactory.create(
            wallet=wallet,
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.FAILED,
        )

        call_command("backfill_balances")

        assert BalanceTransaction.objects.count() == 0
        wallet.refresh_from_db()
        assert wallet.operational_balance == 0

    def test_command_is_idempotent_and_skips_existing_transactions(self):
        """
        Idempotency Test: Ensures that running the command multiple
        times will not create duplicate audit records.
        """
        wallet = CurrencyWalletFactory.create(operational_balance=0)
        trx_to_migrate = PaymentTransactionFactory.create(
            wallet=wallet,
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.SUCCESS,
        )
        trx_to_skip = PaymentTransactionFactory.create(
            wallet=wallet,
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.SUCCESS,
        )

        BalanceTransactionFactory.create(
            payment_transaction=trx_to_skip,
            type=BalanceEventType.OPERATION_CONFIRMED,
        )

        assert BalanceTransaction.objects.count() == 1

        call_command("backfill_balances")

        assert BalanceTransaction.objects.count() == 3
        assert (
            BalanceTransaction.objects.filter(
                payment_transaction=trx_to_migrate
            ).count()
            == 2
        )
        assert (
            BalanceTransaction.objects.filter(payment_transaction=trx_to_skip).count()
            == 1
        )

        call_command("backfill_balances")

        assert BalanceTransaction.objects.count() == 3

    def test_dry_run_makes_no_database_changes(self, capsys):
        """
        Safety Test: Verifies that the --dry-run flag prevents any
        and all database modifications.
        """
        wallet = CurrencyWalletFactory.create(operational_balance=Decimal("100.00"))
        PaymentTransactionFactory.create(
            wallet=wallet,
            type=TransactionType.DEPOSIT,
            status=TransactionStatus.SUCCESS,
            amount=Decimal("50.00"),
        )

        call_command("backfill_balances", dry_run=True)

        assert BalanceTransaction.objects.count() == 0
        wallet.refresh_from_db()
        assert wallet.operational_balance == Decimal("100.00")

        captured = capsys.readouterr()
        assert "[Dry Run] Would CREATE missing event" in captured.out
        assert str(BalanceEventType.OPERATION_CONFIRMED) in captured.out
