from decimal import Decimal
from logging import Logger
from unittest import mock
from unittest.mock import call, patch

import pytest
from bm.datatypes import Money
from rozert_pay.common import const
from rozert_pay.payment import tasks
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services import db_services, withdraw_services
from rozert_pay.payment.systems.base_controller import PaymentSystemController
from rozert_pay.payment.systems.paycash import PaycashClient, paycash_controller
from rozert_pay.payment.systems.paypal import PaypalClient, paypal_controller
from tests.factories import (
    PaymentClientWithdrawResponseFactory,
    PaymentTransactionFactory,
    RemoteTransactionStatusFactory,
)


@pytest.mark.django_db
class TestBaseController:
    def test_run_deposit_finalization_error(self, disable_error_logs):
        trx: PaymentTransaction = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
        )
        with patch.object(
            PaypalClient, "deposit_finalize", side_effect=Exception("olala")
        ):
            paypal_controller.run_deposit_finalization(trx.id)
        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.FAILED
        assert trx.decline_code == const.TransactionDeclineCodes.INTERNAL_ERROR
        assert trx.decline_reason is None

    def test_run_deposit(self, disable_error_logs):
        with patch.object(Logger, "info") as info_mck:
            trx: PaymentTransaction = PaymentTransactionFactory.create(
                status=const.TransactionStatus.SUCCESS
            )
            paycash_controller.run_deposit(trx.id)
            trx.refresh_from_db()
            assert trx.status == const.TransactionStatus.SUCCESS
            assert info_mck.call_args == call(
                "Transaction is not in initial status",
            )

        with patch.object(Logger, "info") as info_mck:
            trx = PaymentTransactionFactory.create(
                status=const.TransactionStatus.FAILED
            )
            paycash_controller.run_deposit(trx.id)
            trx.refresh_from_db()
            assert trx.status == const.TransactionStatus.FAILED
            assert info_mck.call_args == call(
                "Transaction is not in initial status",
            )

        with patch.object(Logger, "error") as mck:
            trx = PaymentTransactionFactory.create(
                status=const.TransactionStatus.PENDING,
                type=const.TransactionType.WITHDRAWAL,
            )
            paycash_controller.run_deposit(trx.id)
            trx.refresh_from_db()
            assert trx.status == const.TransactionStatus.PENDING
            assert mck.call_args == call(
                "Transaction is not a deposit",
            )

    def test_run_deposit_with_exception(self, disable_error_logs):
        with patch.object(
            PaymentSystemController, "_run_deposit", side_effect=Exception
        ):
            trx: PaymentTransaction = PaymentTransactionFactory.create(
                status=const.TransactionStatus.PENDING
            )
            paycash_controller.run_deposit(trx.id)
            trx.refresh_from_db()
            assert trx.status == const.TransactionStatus.FAILED
            assert trx.decline_code == const.TransactionDeclineCodes.INTERNAL_ERROR
            assert trx.paymenttransactioneventlog_set.count() == 1

    def test_sync_remote_status_with_transaction_deposit(self):
        trx: db_services.LockedTransaction = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.DEPOSIT,
        )
        remote_status = RemoteTransactionStatusFactory.build()
        paycash_controller.sync_remote_status_with_transaction(
            trx=trx,
            remote_status=remote_status,
        )

        # Remote status is final but not matched with transaction status
        trx.status = const.TransactionStatus.SUCCESS
        remote_status.operation_status = const.TransactionStatus.FAILED

        with pytest.raises(AssertionError):
            paycash_controller.sync_remote_status_with_transaction(
                trx=trx,
                remote_status=remote_status,
            )

        # Remote status is pending, our is final
        remote_status.operation_status = const.TransactionStatus.PENDING
        with pytest.raises(AssertionError):
            paycash_controller.sync_remote_status_with_transaction(
                trx=trx,
                remote_status=remote_status,
            )

    def test_sync_remote_status_with_transaction_deposit_decline(self):
        trx: db_services.LockedTransaction = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.DEPOSIT,
        )
        remote_status = RemoteTransactionStatusFactory.build(
            decline_code="decline_code",
            decline_reason="decline_reason",
            operation_status=const.TransactionStatus.FAILED,
        )
        paycash_controller.sync_remote_status_with_transaction(
            trx=trx,
            remote_status=remote_status,
        )

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.FAILED
        assert trx.decline_code == "decline_code"
        assert trx.decline_reason == "decline_reason"

        # Another decline codes
        trx.status = const.TransactionStatus.PENDING
        trx.save()

        with pytest.raises(AssertionError):
            remote_status.decline_code = "another_decline_code"
            paycash_controller.sync_remote_status_with_transaction(
                trx=trx,
                remote_status=remote_status,
            )

        remote_status.decline_code = "decline_code"

        # Another decline reasons
        with pytest.raises(AssertionError):
            remote_status.decline_reason = "another_decline_reason"
            paycash_controller.sync_remote_status_with_transaction(
                trx=trx,
                remote_status=remote_status,
            )

    def test_sync_remote_status_with_transaction_deposit_approve(self):
        trx: db_services.LockedTransaction = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.DEPOSIT,
            amount=Decimal("123.12"),
            wallet__operational_balance=Decimal("100.00"),
            wallet__pending_balance=Decimal("0.00"),
            wallet__frozen_balance=Decimal("0.00"),
        )
        assert trx.wallet.operational_balance == 100
        assert trx.wallet.frozen_balance == 0

        remote_status = RemoteTransactionStatusFactory.build(
            operation_status=const.TransactionStatus.SUCCESS,
        )
        paycash_controller.sync_remote_status_with_transaction(
            trx=trx,
            remote_status=remote_status,
        )

        trx.wallet.refresh_from_db()
        assert trx.status == const.TransactionStatus.SUCCESS
        assert trx.wallet.operational_balance == Decimal("223.12")
        # The pending balance is settled immediately returning to zero
        assert trx.wallet.pending_balance == Decimal("0.00")
        assert trx.wallet.frozen_balance == 0

        # Second approve - no effect
        paycash_controller.sync_remote_status_with_transaction(
            trx=trx,
            remote_status=remote_status,
        )

        trx.wallet.refresh_from_db()
        assert trx.status == const.TransactionStatus.SUCCESS
        assert trx.wallet.operational_balance == Decimal("223.12")
        assert trx.wallet.pending_balance == Decimal("0.00")
        assert trx.wallet.frozen_balance == 0

    def test_sync_remote_status_with_transaction_payout_approve(
        self, disable_error_logs
    ):
        trx: db_services.LockedTransaction = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.WITHDRAWAL,
            amount=Decimal("100.00"),
            wallet__operational_balance=Decimal("1000.00"),
            wallet__frozen_balance=Decimal("100.00"),
        )
        remote_status = RemoteTransactionStatusFactory.build(
            operation_status=const.TransactionStatus.SUCCESS,
        )
        paycash_controller.sync_remote_status_with_transaction(
            trx=trx,
            remote_status=remote_status,
        )

        trx.wallet.refresh_from_db()
        assert trx.status == const.TransactionStatus.SUCCESS
        assert trx.wallet.operational_balance == Decimal("900.00")
        assert trx.wallet.frozen_balance == Decimal("0.00")

    def test_sync_remote_status_with_transaction_payout_decline(
        self, disable_error_logs
    ):
        trx: db_services.LockedTransaction = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.WITHDRAWAL,
            amount=Decimal("100.00"),
            wallet__operational_balance=Decimal("1000.00"),
            wallet__frozen_balance=Decimal("100.00"),
        )
        remote_status = RemoteTransactionStatusFactory.build(
            operation_status=const.TransactionStatus.FAILED,
        )
        paycash_controller.sync_remote_status_with_transaction(
            trx=trx,
            remote_status=remote_status,
        )

        trx.wallet.refresh_from_db()
        assert trx.status == const.TransactionStatus.FAILED
        assert trx.wallet.operational_balance == Decimal("1000.00")
        assert trx.wallet.frozen_balance == Decimal("0.00")

    def test_run_withdraw_success(self):
        trx = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.WITHDRAWAL,
        )
        with patch.object(
            paycash_controller,
            "_run_withdraw",
            return_value=PaymentClientWithdrawResponseFactory.build(),
        ):
            paycash_controller.run_withdraw(trx.id)

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.PENDING

        # Not pending status
        with patch.object(Logger, "info") as info_mck:
            trx.status = const.TransactionStatus.SUCCESS
            trx.save()
            paycash_controller.run_withdraw(trx.id)
            assert info_mck.call_args == call(
                "Transaction is not in initial status",
            )

        # Not withdrawal type
        with patch.object(Logger, "error") as mck:
            trx.status = const.TransactionStatus.PENDING
            trx.type = const.TransactionType.DEPOSIT
            trx.save()
            paycash_controller.run_withdraw(trx.id)
            assert mck.call_args == call(
                "Transaction is not a withdrawal",
            )

    def test_run_withdraw_decline(self):
        # Even if we get a decline response, we should not change the status of the withdrawal transaction.
        # Status is changed only after querying payment system.
        trx = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.WITHDRAWAL,
        )
        with patch.object(
            paycash_controller,
            "_run_withdraw",
            return_value=PaymentClientWithdrawResponseFactory.build(
                operation_status=const.TransactionStatus.FAILED
            ),
        ):
            paycash_controller.run_withdraw(trx.id)

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.PENDING

    def test_run_withdraw_error(self, disable_error_logs):
        # Even if we get a decline response, we should not change the status of the withdrawal transaction.
        # Status is changed only after querying payment system.
        trx = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.WITHDRAWAL,
        )
        with patch.object(
            paycash_controller, "_run_withdraw", side_effect=Exception("some error")
        ):
            paycash_controller.run_withdraw(trx.id)

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.PENDING
        assert list(
            trx.paymenttransactioneventlog_set.values(
                "event_type", "extra", "description"
            )
        ) == [
            {
                "description": "Error during withdrawal processing: some error",
                "event_type": "error",
                "extra": {"message": "some error", "trace": mock.ANY},
            }
        ]

    def test_execute_withdraw_query(self):
        trx = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.WITHDRAWAL,
            amount=Decimal("100.00"),
            wallet__operational_balance=Decimal("1000.00"),
            wallet__frozen_balance=Decimal("100.00"),
        )

        with patch.object(
            PaycashClient,
            "withdraw",
            return_value=PaymentClientWithdrawResponseFactory.build(),
        ):
            with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
                trx,
                paycash_controller,
                schedule_check_immediately=False,
            ):
                pass

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.PENDING

        # check status
        with patch.object(PaycashClient, "get_transaction_status") as mck:
            mck.return_value = RemoteTransactionStatusFactory.build(
                operation_status=const.TransactionStatus.SUCCESS,
                remote_amount=Money(trx.amount, trx.currency),
            )
            tasks.check_status(trx.id)

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.SUCCESS
        assert trx.wallet.operational_balance == Decimal("900.00")
        assert trx.wallet.frozen_balance == Decimal("0.00")

    def test_execute_withdraw_query_failed(self):
        trx = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.WITHDRAWAL,
            amount=Decimal("100.00"),
            wallet__operational_balance=Decimal("100.00"),
            wallet__frozen_balance=Decimal("100.00"),
        )

        with patch.object(
            PaycashClient,
            "withdraw",
            return_value=PaymentClientWithdrawResponseFactory.build(
                status=const.TransactionStatus.FAILED,
                decline_code="123",
            ),
        ):
            with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
                trx, paycash_controller
            ):
                pass

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.FAILED
        assert trx.wallet.operational_balance == Decimal("100.00")
        assert trx.wallet.frozen_balance == Decimal("0.00")
