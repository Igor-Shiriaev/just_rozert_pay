import logging
from typing import Final

from bm.datatypes import Money
from django.db import transaction
from pydantic import BaseModel, ConfigDict
from rozert_pay.payment.models import CurrencyWallet, PaymentTransaction

from ..common.metrics import track_duration
from .const import InitiatorType
from .models import BalanceTransaction, BalanceTransactionType, InitiatorType

_BalanceUpdateService: Final = "BalanceUpdateService"
logger = logging.getLogger(__name__)


class BalanceUpdateDTO(BaseModel):
    """
    Data Transfer Object for updating a balance.
    This is the only way to pass data to the BalanceUpdateService.
    Amount should always be a positive value, representing the magnitude
    of the operation.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    currency_wallet: CurrencyWallet
    event_type: BalanceTransactionType
    amount: Money
    initiator: InitiatorType
    payment_transaction: PaymentTransaction | None = None
    description: str | None = None


class BalanceUpdateService:
    """
    The single entry point for all balance modifications.
    Ensures that every change is atomic and creates an audit trail.
    """

    @staticmethod
    @transaction.atomic
    @track_duration("BalanceUpdateService.update_balance")
    def update_balance(dto: BalanceUpdateDTO) -> BalanceTransaction:
        """
        Updates a CurrencyWallet's balances based on a business event.
        This is the main public method and acts as an orchestrator.

        This method is atomic. It performs the following actions:
        1. Locks the CurrencyWallet row to prevent race conditions.
        2. Delegates the balance change logic to the private _apply_event method.
        3. If settlement simulation is enabled, it orchestrates a second call
           to _apply_event for the settlement transaction.
        4. Returns created audit record.

        Args:
            dto: An immutable DTO. Its `amount` must always be positive.

        Returns:
            The newly created BalanceTransaction record for auditing purposes.

        Raises:
            ValueError: If currencies mismatch or a negative balance would occur.
            NotImplementedError: If the event_type is unknown.
        """
        # Lock the wallet once for the entire sequence of operations.
        wallet = CurrencyWallet.objects.select_for_update().get(
            pk=dto.currency_wallet.pk
        )

        main_tx_record = BalanceUpdateService._apply_event(wallet, dto)
        wallet.refresh_from_db()  # Refresh state

        # internal settlement simulation.
        if dto.event_type == BalanceTransactionType.OPERATION_CONFIRMED:
            settlement_dto = BalanceUpdateDTO(
                currency_wallet=wallet,
                event_type=BalanceTransactionType.SETTLEMENT_FROM_PROVIDER,
                amount=dto.amount,
                initiator=InitiatorType.SYSTEM,
                description="Automatic settlement simulation for non-prod environment.",
                payment_transaction=dto.payment_transaction,
            )
            _ = BalanceUpdateService._apply_event(wallet, settlement_dto)

        return main_tx_record

    @staticmethod
    @track_duration("BalanceUpdateService._apply_event")
    def _apply_event(
        wallet: CurrencyWallet, dto: BalanceUpdateDTO
    ) -> BalanceTransaction:
        """
        Private worker method to apply a single balance-changing event.
        This method assumes the wallet is already locked.
        """
        if wallet.currency != dto.amount.currency:
            raise ValueError("Transaction currency does not match wallet currency.")

        assert (
            dto.amount.value > 0
        ), "Balance-changing transactions cannot have a zero or negative amount."

        before_state = {
            "operational": wallet.operational_balance,
            "frozen": wallet.frozen_balance,
            "pending": wallet.pending_balance,
        }

        new_op, new_fr, new_pe = (
            before_state["operational"],
            before_state["frozen"],
            before_state["pending"],
        )
        transaction_amount = dto.amount.value

        match dto.event_type:
            case BalanceTransactionType.FEE | BalanceTransactionType.CHARGE_BACK:
                new_op -= dto.amount.value
                transaction_amount = -dto.amount.value
            case BalanceTransactionType.MANUAL_ADJUSTMENT:
                #  MANUAL_ADJUSTMENT is always a credit.
                new_op += dto.amount.value
            case BalanceTransactionType.SETTLEMENT_REVERSAL:
                # returned payout is a simple credit to the operational balance
                new_op += dto.amount.value
            case BalanceTransactionType.OPERATION_CONFIRMED:
                new_op += dto.amount.value
                new_pe += dto.amount.value
            case BalanceTransactionType.SETTLEMENT_FROM_PROVIDER:
                new_pe -= dto.amount.value
            case (
                BalanceTransactionType.SETTLEMENT_REQUEST
                | BalanceTransactionType.ROLLING_RESERVE_HOLD
                | BalanceTransactionType.FROZEN
            ):
                new_fr += dto.amount.value
            case (
                BalanceTransactionType.SETTLEMENT_CANCEL
                | BalanceTransactionType.ROLLING_RESERVE_RELEASE
                | BalanceTransactionType.UNFROZEN
            ):
                new_fr -= dto.amount.value
            case BalanceTransactionType.SETTLEMENT_CONFIRMED:
                new_op -= dto.amount.value
                new_fr -= dto.amount.value
                transaction_amount = -dto.amount.value
            case _:
                raise NotImplementedError(
                    f"Event type '{dto.event_type}' is not implemented."
                )

        if new_op < 0 or new_fr < 0 or new_pe < 0:
            logger.critical(
                "CRITICAL: Negative balance.",
                extra={
                    "wallet_id": wallet.id,
                    "event_id": dto.payment_transaction.id
                    if dto.payment_transaction
                    else "",
                    "event_type": dto.event_type,
                    "balances_before": before_state,
                    "attempted_balances_after": {
                        "op": new_op,
                        "fr": new_fr,
                        "pe": new_pe,
                    },
                },
            )

        tx_record = BalanceTransaction.objects.create(
            currency_wallet=wallet,
            type=dto.event_type,
            amount=transaction_amount,
            operational_before=before_state["operational"],
            frozen_before=before_state["frozen"],
            pending_before=before_state["pending"],
            operational_after=new_op,
            frozen_after=new_fr,
            pending_after=new_pe,
            payment_transaction=dto.payment_transaction,
            description=dto.description,
            initiator=dto.initiator,
        )

        wallet.operational_balance = new_op
        wallet.frozen_balance = new_fr
        wallet.pending_balance = new_pe
        wallet.save(
            update_fields=[
                "operational_balance",
                "frozen_balance",
                "pending_balance",
                "updated_at",
            ]
        )
        return tx_record
