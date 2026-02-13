from decimal import Decimal

import pytest
from rozert_pay.common.const import TransactionStatus, TransactionType
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services.transaction_set_status import DefaultTransactionSetter
from tests.factories import PaymentTransactionFactory


class TestTransactionSetStatus:
    @pytest.mark.parametrize(
        "case",
        [
            # Case 1: Successful Deposit (PENDING -> SUCCESS)
            # Fires OPERATION_CONFIRMED (+op, +pen) AND simulated SETTLEMENT_FROM_PROVIDER (-pen)
            {
                "type": TransactionType.DEPOSIT,
                "status": TransactionStatus.PENDING,
                "target": TransactionStatus.SUCCESS,
                "expected_op": "110.00",
                "expected_fr": "10.00",
                "expected_pen": "0.00",
            },
            # Case 2: Reverting a Successful Deposit (SUCCESS -> FAILED)
            # Fires revert_to_pending which uses CHARGEBACK event (op -= amount)
            {
                "type": TransactionType.DEPOSIT,
                "status": TransactionStatus.SUCCESS,
                "target": TransactionStatus.FAILED,
                "expected_op": "90.00",
                "expected_fr": "10.00",
                "expected_pen": "0.00",
            },
            # Case 3: Successful Withdrawal (PENDING -> SUCCESS)
            # Fires SETTLEMENT_CONFIRMED event (op -= amount, fr -= amount)
            {
                "type": TransactionType.WITHDRAWAL,
                "status": TransactionStatus.PENDING,
                "target": TransactionStatus.SUCCESS,
                "expected_op": "90.00",
                "expected_fr": "0.00",
                "expected_pen": "0.00",
            },
            # Case 4: Reverting a Successful Withdrawal (SUCCESS -> FAILED)
            # 1. Revert (SUCCESS -> PENDING): Fires MANUAL_ADJUSTMENT (op += amount) -> op=110, fr=10
            # 2. Fail (PENDING -> FAILED): Fires SETTLEMENT_CANCEL (fr -= amount) -> fr=0
            {
                "type": TransactionType.WITHDRAWAL,
                "status": TransactionStatus.SUCCESS,
                "target": TransactionStatus.FAILED,
                "expected_op": "110.00",
                "expected_fr": "0.00",
                "expected_pen": "0.00",
            },
        ],
    )
    def test_status_change_updates_balances_correctly(
        self, wallet_paycash, admin_user, case
    ):
        initial_op = Decimal("100.00")
        initial_fr = Decimal("10.00")
        initial_pen = Decimal("0.00")

        trx: PaymentTransaction = PaymentTransactionFactory.create(
            wallet__wallet=wallet_paycash,
            wallet__operational_balance=initial_op,
            wallet__frozen_balance=initial_fr,
            wallet__pending_balance=initial_pen,
            amount=10,
            type=case["type"],
            status=case["status"],
        )

        setter = DefaultTransactionSetter(trx, admin_user)
        res = setter.save_form(
            {
                "status": case["target"],
                "comment": "test comment",
                "approve": True,
            }
        )
        assert res is None, "save_form should not return an error"

        trx.refresh_from_db()
        trx.wallet.refresh_from_db()

        assert trx.status == case["target"]
        assert trx.wallet.operational_balance == Decimal(case["expected_op"])
        assert trx.wallet.frozen_balance == Decimal(case["expected_fr"])
        assert trx.wallet.pending_balance == Decimal(case["expected_pen"])
