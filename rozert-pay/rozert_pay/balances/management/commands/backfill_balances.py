from decimal import Decimal
from typing import Any

from bm.datatypes import Money
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.db.models import Q
from rozert_pay.balances.const import BalanceTransactionType as BalanceEventType
from rozert_pay.balances.const import InitiatorType
from rozert_pay.balances.models import BalanceTransaction
from rozert_pay.balances.services import BalanceUpdateDTO, BalanceUpdateService
from rozert_pay.common.const import (
    TransactionExtraFields,
    TransactionStatus,
    TransactionType,
)
from rozert_pay.payment.models import PaymentTransaction


class Command(BaseCommand):
    help = (
        "Reconstructs balance history from final-state PaymentTransactions. "
        "This command is idempotent."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the backfill without saving changes.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=500,
            help="The number of transactions to process in a single batch.",
        )
        parser.add_argument(
            "--date-from",
            type=str,
            help="Filter transactions created after this date/time (ISO format).",
        )
        parser.add_argument(
            "--date-to",
            type=str,
            help="Filter transactions created before this date/time (ISO format).",
        )

    def _create_dto(
        self,
        trx: PaymentTransaction,
        event_type: BalanceEventType,
        amount_override: Money | None = None,
    ) -> BalanceUpdateDTO | None:
        amount_money = (
            amount_override
            if amount_override is not None
            else Money(trx.amount.copy_abs(), trx.currency)
        )

        if amount_money.value <= 0:
            return None

        return BalanceUpdateDTO(
            currency_wallet=trx.wallet,
            event_type=event_type,
            amount=amount_money,
            payment_transaction=trx,
            initiator=InitiatorType.SYSTEM,
            description=f"Backfill ({trx.type}) for transaction {trx.id}",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]
        chunk_size = options["chunk_size"]
        date_from = options["date_from"]
        date_to = options["date_to"]

        self.stdout.write(self.style.NOTICE("Starting balance history backfill..."))
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY-RUN mode. No database changes will be made.")
            )

        q_finalized = Q(
            status__in=[
                TransactionStatus.SUCCESS,
                TransactionStatus.FAILED,
                TransactionStatus.CHARGED_BACK,
                TransactionStatus.REFUNDED,
            ]
        )
        q_pending_withdrawal = Q(
            status=TransactionStatus.PENDING, type=TransactionType.WITHDRAWAL
        )

        base_queryset = PaymentTransaction.objects.filter(
            q_finalized | q_pending_withdrawal
        )

        if date_from:
            base_queryset = base_queryset.filter(created_at__gte=date_from)
        if date_to:
            base_queryset = base_queryset.filter(created_at__lte=date_to)

        total_transactions = base_queryset.count()
        if not total_transactions:
            self.stdout.write(
                self.style.SUCCESS("No payment transactions require migration.")
            )
            return

        self.stdout.write(f"Found {total_transactions} transactions to process.")

        processed_count = 0
        last_processed_id = 0

        while True:
            current_batch_qs = (
                base_queryset.filter(id__gt=last_processed_id)
                .select_related("wallet")
                .order_by("id")[:chunk_size]
            )

            current_batch = list(current_batch_qs)

            if not current_batch:
                break

            for trx in current_batch:
                last_processed_id = trx.id

                try:
                    potential_dtos: list[BalanceUpdateDTO | None] = []

                    if trx.type == TransactionType.DEPOSIT:
                        if trx.status == TransactionStatus.SUCCESS:
                            if trx.extra.get(
                                TransactionExtraFields.IS_CHARGEBACK_REVERSAL_RECEIVED
                            ):
                                potential_dtos.extend(
                                    [
                                        self._create_dto(
                                            trx, BalanceEventType.OPERATION_CONFIRMED
                                        ),
                                        self._create_dto(
                                            trx, BalanceEventType.CHARGE_BACK
                                        ),
                                        self._create_dto(
                                            trx, BalanceEventType.MANUAL_ADJUSTMENT
                                        ),
                                    ]
                                )
                            else:
                                potential_dtos.append(
                                    self._create_dto(
                                        trx, BalanceEventType.OPERATION_CONFIRMED
                                    )
                                )

                        elif trx.status == TransactionStatus.CHARGED_BACK:
                            potential_dtos.extend(
                                [
                                    self._create_dto(
                                        trx, BalanceEventType.OPERATION_CONFIRMED
                                    ),
                                    self._create_dto(trx, BalanceEventType.CHARGE_BACK),
                                ]
                            )

                        elif trx.status == TransactionStatus.REFUNDED:
                            refund_amount_str = trx.extra.get(
                                TransactionExtraFields.REFUNDED_AMOUNT
                            )
                            refund_money = (
                                Money(Decimal(refund_amount_str), trx.currency)
                                if refund_amount_str
                                else Money(trx.amount.copy_abs(), trx.currency)
                            )
                            potential_dtos.extend(
                                [
                                    self._create_dto(
                                        trx, BalanceEventType.OPERATION_CONFIRMED
                                    ),
                                    self._create_dto(
                                        trx,
                                        BalanceEventType.CHARGE_BACK,
                                        amount_override=refund_money,
                                    ),
                                ]
                            )

                        elif trx.status == TransactionStatus.FAILED:
                            pass

                    elif trx.type == TransactionType.WITHDRAWAL:
                        if trx.status == TransactionStatus.PENDING:
                            potential_dtos.append(
                                self._create_dto(
                                    trx, BalanceEventType.SETTLEMENT_REQUEST
                                )
                            )
                        elif trx.status == TransactionStatus.SUCCESS:
                            potential_dtos.extend(
                                [
                                    self._create_dto(
                                        trx, BalanceEventType.SETTLEMENT_REQUEST
                                    ),
                                    self._create_dto(
                                        trx, BalanceEventType.SETTLEMENT_CONFIRMED
                                    ),
                                ]
                            )
                        elif trx.status == TransactionStatus.FAILED:
                            potential_dtos.extend(
                                [
                                    self._create_dto(
                                        trx, BalanceEventType.SETTLEMENT_REQUEST
                                    ),
                                    self._create_dto(
                                        trx, BalanceEventType.SETTLEMENT_CANCEL
                                    ),
                                ]
                            )

                    dtos_to_process: list[BalanceUpdateDTO] = []
                    valid_dtos = [dto for dto in potential_dtos if dto is not None]

                    for dto in valid_dtos:
                        event_exists = BalanceTransaction.objects.filter(
                            payment_transaction=trx, type=dto.event_type
                        ).exists()

                        if not event_exists:
                            dtos_to_process.append(dto)
                        elif dry_run:
                            self.stdout.write(
                                self.style.NOTICE(
                                    f"[Dry Run] SKIPPING existing event: "
                                    f"TrxID {trx.id}, Type {dto.event_type}"
                                )
                            )

                    if not dtos_to_process:
                        processed_count += 1
                        continue

                    if dry_run:
                        for dto in dtos_to_process:
                            self.stdout.write(
                                f"[Dry Run] Would CREATE missing event: "
                                f"TrxID {trx.id}, Type {dto.event_type}, Amount {dto.amount.value}"
                            )
                        processed_count += 1
                        continue

                    with transaction.atomic():
                        for dto in dtos_to_process:
                            BalanceUpdateService.update_balance(dto)

                    processed_count += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to process PaymentTransaction {trx.id}: {e}"
                        )
                    )

            self.stdout.write(f"Processed {processed_count}/{total_transactions}...")

        final_msg = (
            f"Dry run complete. Processed {processed_count} transactions."
            if dry_run
            else f"Backfill complete. Successfully processed {processed_count} transactions."
        )
        self.stdout.write(self.style.SUCCESS(final_msg))
