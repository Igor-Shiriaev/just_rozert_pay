import logging
from decimal import Decimal

import pytest
from bm.datatypes import Money
from rozert_pay.balances.const import BalanceTransactionType, InitiatorType
from rozert_pay.balances.models import BalanceTransaction
from rozert_pay.balances.services import BalanceUpdateDTO, BalanceUpdateService
from rozert_pay.payment.models import CurrencyWallet
from tests.factories import CurrencyWalletFactory, PaymentTransactionFactory

pytestmark = pytest.mark.django_db


class TestBalanceUpdateService:
    """
    Tests for the BalanceUpdateService, focusing on core business logic
    and adherence to the established architectural contract.
    """

    def test_operation_confirmed_with_simulated_settlement_creates_two_records(self):
        """
        Business Logic: Verifies the most complex flow - a deposit that
        triggers an immediate, simulated settlement. This is a core feature
        of the non-production environment.
        """
        wallet: CurrencyWallet = CurrencyWalletFactory.create(
            operational_balance=Decimal("1000.00"),
            pending_balance=Decimal("100.00"),
            frozen_balance=Decimal("50.00"),
            currency="USD",
        )
        amount = Money("200.00", "USD")
        linked_op = PaymentTransactionFactory.create()
        dto = BalanceUpdateDTO(
            currency_wallet=wallet,
            event_type=BalanceTransactionType.OPERATION_CONFIRMED,
            amount=amount,
            initiator=InitiatorType.SYSTEM,
            payment_transaction=linked_op,
            description="Test deposit",
        )

        # called once, but performs two operations internally
        tx_record = BalanceUpdateService.update_balance(dto)

        wallet.refresh_from_db()
        # Step 1 (OPERATION_CONFIRMED): op +200, pen +200 -> op=1200, pen=300
        # Step 2 (SETTLEMENT_FROM_PROVIDER): pen -200 -> pen=100
        assert wallet.operational_balance == Decimal("1200.00")
        assert wallet.pending_balance == Decimal("100.00")  # back to original value
        assert wallet.frozen_balance == Decimal("50.00")

        # Verify that two transaction records were created for full auditability
        assert BalanceTransaction.objects.count() == 2

        # Verify the primary transaction record returned to the caller
        assert tx_record.type == BalanceTransactionType.OPERATION_CONFIRMED
        assert tx_record.amount == Decimal("200.00")
        assert tx_record.operational_before == Decimal("1000.00")
        assert tx_record.operational_after == Decimal("1200.00")
        assert tx_record.pending_before == Decimal("100.00")
        assert tx_record.pending_after == Decimal("300.00")

        # Verify the simulated transaction record
        simulated_tx = BalanceTransaction.objects.first()
        assert simulated_tx is not None
        assert simulated_tx.type == BalanceTransactionType.SETTLEMENT_FROM_PROVIDER
        assert simulated_tx.amount == Decimal("200.00")
        assert simulated_tx.operational_before == Decimal("1200.00")
        assert simulated_tx.operational_after == Decimal("1200.00")
        assert simulated_tx.pending_before == Decimal("300.00")
        assert simulated_tx.pending_after == Decimal("100.00")

    @pytest.mark.parametrize(
        "event_type, initial_op, expected_op, expected_tx_amount",
        [
            (BalanceTransactionType.FEE, "1000.00", "994.50", "-5.50"),
            (BalanceTransactionType.CHARGE_BACK, "1000.00", "850.00", "-150.00"),
        ],
    )
    def test_debit_operations(
        self, event_type, initial_op, expected_op, expected_tx_amount
    ):
        """
        Business Logic: Ensures that debit operations correctly decrease
        the operational balance and record a negative amount in the audit trail.
        """
        wallet: CurrencyWallet = CurrencyWalletFactory.create(
            operational_balance=Decimal(initial_op), currency="EUR"
        )
        # DTO amount is positive per service contract
        amount = Money(str(abs(Decimal(expected_tx_amount))), "EUR")
        dto = BalanceUpdateDTO(
            currency_wallet=wallet,
            event_type=event_type,
            amount=amount,
            initiator=InitiatorType.SYSTEM,
        )

        tx = BalanceUpdateService.update_balance(dto)

        wallet.refresh_from_db()
        assert wallet.operational_balance == Decimal(expected_op)
        assert tx.amount == Decimal(expected_tx_amount)
        assert tx.operational_before == Decimal(initial_op)
        assert tx.operational_after == Decimal(expected_op)

    def test_settlement_confirmed_debits_operational_and_frozen(self):
        """
        Business Logic: Verifies that confirming a settlement correctly
        debits both total funds (operational) and locked funds (frozen).
        """
        wallet: CurrencyWallet = CurrencyWalletFactory.create(
            operational_balance=Decimal("1000.00"),
            frozen_balance=Decimal("300.00"),
            currency="GBP",
        )
        dto = BalanceUpdateDTO(
            currency_wallet=wallet,
            event_type=BalanceTransactionType.SETTLEMENT_CONFIRMED,
            amount=Money("300.00", "GBP"),
            initiator=InitiatorType.SERVICE,
        )

        tx = BalanceUpdateService.update_balance(dto)

        wallet.refresh_from_db()
        assert wallet.operational_balance == Decimal("700.00")
        assert wallet.frozen_balance == Decimal("0.00")
        assert tx.amount == Decimal("-300.00")

    def test_mismatched_currency_raises_value_error(self):
        """Contract Test: Ensures the service rejects transactions where
        the amount currency differs from the wallet currency."""
        wallet: CurrencyWallet = CurrencyWalletFactory.create(currency="USD")
        dto = BalanceUpdateDTO(
            currency_wallet=wallet,
            event_type=BalanceTransactionType.FEE,
            amount=Money("10.00", "EUR"),  # Mismatched currency
            initiator=InitiatorType.SYSTEM,
        )

        with pytest.raises(
            ValueError, match="Transaction currency does not match wallet currency."
        ):
            BalanceUpdateService.update_balance(dto)

    def test_negative_dto_amount_raises_value_error(self):
        """Contract Test: Enforces the rule that the DTO must always
        contain a positive amount."""
        wallet: CurrencyWallet = CurrencyWalletFactory.create(currency="USD")
        with pytest.raises(AssertionError):
            BalanceUpdateService.update_balance(
                BalanceUpdateDTO(
                    currency_wallet=wallet,
                    event_type=BalanceTransactionType.FEE,
                    amount=Money("-10.00", "USD"),  # Negative amount
                    initiator=InitiatorType.SYSTEM,
                )
            )

    def test_operation_resulting_in_negative_balance_is_allowed_and_logged(
        self, caplog, disable_error_logs
    ):
        """
        Business Logic (Edge Case): This test CONFIRMS the decision to ALLOW
        negative balances. It verifies that the operation completes and that
        a CRITICAL log message is generated as a result.
        """
        wallet: CurrencyWallet = CurrencyWalletFactory.create(
            operational_balance=Decimal("100.00"), currency="USD"
        )
        amount = Money("150.00", "USD")  # Amount larger than balance
        dto = BalanceUpdateDTO(
            currency_wallet=wallet,
            event_type=BalanceTransactionType.CHARGE_BACK,
            amount=amount,
            initiator=InitiatorType.SYSTEM,
        )

        with caplog.at_level(logging.CRITICAL):
            BalanceUpdateService.update_balance(dto)

        wallet.refresh_from_db()
        #  negative balance was set
        assert wallet.operational_balance == Decimal("-50.00")

        # alert was logged.
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "CRITICAL"
        assert "CRITICAL: Negative balance." in record.message
        assert hasattr(record, "wallet_id")
        assert record.wallet_id == wallet.id
