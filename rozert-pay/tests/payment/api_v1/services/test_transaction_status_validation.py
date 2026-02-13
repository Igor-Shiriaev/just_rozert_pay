import pytest
from bm.datatypes import Money
from rozert_pay.common import const
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services import errors, transaction_status_validation
from tests.factories import PaymentTransactionFactory


@pytest.mark.django_db
class TestTransactionValidation:
    def test_deposit_amounts_validation(self):
        success_deposit = PaymentTransactionFactory.create(
            amount=100.01,
            currency="MXN",
            type=const.TransactionType.DEPOSIT,
        )

        self.assertError(
            trx=success_deposit,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=Money(100.02, "MXN"),
            expect_error="Amount mismatch: 100.01 != 100.02",
        )
        self.assertError(
            trx=success_deposit,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=Money(100.00, "MXN"),
            expect_error="Amount mismatch: 100.01 != 100.0",
        )
        self.assertError(
            trx=success_deposit,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=Money(100.01, "RUB"),
            expect_error="Other currency RUB is not equal to MXN",
        )
        self.assertError(
            trx=success_deposit,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=None,
            expect_error="Remote amount is not provided",
        )

        self.assertOk(
            trx=success_deposit,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=Money(100.011, "MXN"),
        )
        self.assertOk(
            trx=success_deposit,
            operation_status=const.TransactionStatus.FAILED,
            remote_amount=Money(100, "MXN"),
        )
        self.assertOk(
            trx=success_deposit,
            operation_status=const.TransactionStatus.FAILED,
            remote_amount=None,
        )

    def test_withdraw_validation(self):
        withdraw = PaymentTransactionFactory.create(
            amount=100.01,
            currency="MXN",
            type=const.TransactionType.WITHDRAWAL,
        )

        self.assertError(
            trx=withdraw,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=Money(100.02, "MXN"),
            expect_error="Amount mismatch: 100.01 != 100.02",
        )
        self.assertError(
            trx=withdraw,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=Money(100.00, "MXN"),
            expect_error="Amount mismatch: 100.01 != 100.0",
        )
        self.assertError(
            trx=withdraw,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=Money(100.01, "RUB"),
            expect_error="Other currency RUB is not equal to MXN",
        )
        self.assertError(
            trx=withdraw,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=None,
            expect_error="Remote amount is not provided",
        )

        self.assertOk(
            trx=withdraw,
            operation_status=const.TransactionStatus.SUCCESS,
            remote_amount=Money(100.011, "MXN"),
        )
        self.assertError(
            trx=withdraw,
            operation_status=const.TransactionStatus.FAILED,
            remote_amount=Money(100, "MXN"),
            expect_error="Amount mismatch: 100.01 != 100",
        )
        self.assertError(
            trx=withdraw,
            operation_status=const.TransactionStatus.FAILED,
            remote_amount=None,
            expect_error="Remote amount is not provided",
        )

    def assertError(
        self,
        trx: PaymentTransaction,
        operation_status: const.TransactionStatus,
        remote_amount: Money | None,
        expect_error: str,
    ):
        result = transaction_status_validation.validate_remote_transaction_status(
            trx,
            RemoteTransactionStatus(
                raw_data={},
                operation_status=operation_status,
                remote_amount=remote_amount,
                id_in_payment_system="123",
                decline_code="decline",
            ),
        )
        assert isinstance(result, errors.Error)
        assert str(result) == expect_error

    def assertOk(
        self,
        trx: PaymentTransaction,
        operation_status: const.TransactionStatus,
        remote_amount: Money,
    ):
        transaction_status_validation.validate_remote_transaction_status(
            trx,
            RemoteTransactionStatus(
                raw_data={},
                operation_status=operation_status,
                remote_amount=remote_amount,
            ),
        )
