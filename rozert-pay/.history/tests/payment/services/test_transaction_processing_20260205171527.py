import datetime
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from bm.datatypes import Money
from django.db import transaction
from django.utils import timezone
from freezegun import freeze_time
from rozert_pay.common.const import (
    TransactionExtraFields,
    TransactionStatus,
    TransactionType,
)
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.services import db_services, transaction_processing
from rozert_pay.risk_lists.const import Reason, Scope, ValidFor
from rozert_pay.risk_lists.models import BlackListEntry
from rozert_pay.payment.services.transaction_processing import (
    TransactionPeriodicCheckService,
)
from tests.factories import CustomerFactory, PaymentTransactionFactory

pytestmark = pytest.mark.django_db


class TestTransactionPeriodicCheckService:
    def test_schedule(self):
        now = datetime.datetime(2025, 8, 14)

        trx: PaymentTransaction = PaymentTransactionFactory.create()

        with freeze_time(now):
            assert (
                TransactionPeriodicCheckService.should_schedule_check_task_immediately(
                    trx.id, trx.extra
                )
            )
            trx.refresh_from_db()

            assert not TransactionPeriodicCheckService.should_schedule_check_task_immediately(
                trx.id, trx.extra
            )
            trx.refresh_from_db()

        assert trx.extra == {
            "count_status_checks_scheduled": 1,
            "last_status_check_schedule": 1755129600.0,
        }

        with freeze_time(now + timedelta(seconds=55)):
            assert not TransactionPeriodicCheckService.should_schedule_check_task_immediately(
                trx.id, trx.extra
            )
            trx.refresh_from_db()
            assert trx.extra == {
                "count_status_checks_scheduled": 1,
                "last_status_check_schedule": 1755129600.0,
            }

        with freeze_time(now + timedelta(minutes=1)):
            assert (
                TransactionPeriodicCheckService.should_schedule_check_task_immediately(
                    trx.id, trx.extra
                )
            )
            trx.refresh_from_db()
            assert trx.extra == {
                "count_status_checks_scheduled": 2,
                "last_status_check_schedule": 1755129660.0,
            }

        trx.extra[TransactionExtraFields.COUNT_STATUS_CHECKS_SCHEDULED] = 10
        trx.save()

        last_schedule = now + timedelta(minutes=1)

        with freeze_time(last_schedule + timedelta(minutes=4)):
            assert not TransactionPeriodicCheckService.should_schedule_check_task_immediately(
                trx.id, trx.extra
            )
            trx.refresh_from_db()
            assert trx.extra == {
                "count_status_checks_scheduled": 10,
                "last_status_check_schedule": 1755129660.0,
            }

        with freeze_time(last_schedule + timedelta(minutes=5)):
            assert (
                TransactionPeriodicCheckService.should_schedule_check_task_immediately(
                    trx.id, trx.extra
                )
            )
            trx.refresh_from_db()
            assert trx.extra == {
                "count_status_checks_scheduled": 11,
                "last_status_check_schedule": 1755129960.0,
            }

        trx.extra[TransactionExtraFields.COUNT_STATUS_CHECKS_SCHEDULED] = 50
        trx.save()

        last_schedule = timezone.make_aware(
            datetime.datetime.fromtimestamp(1755129960.0)
        )

        with freeze_time(last_schedule + timedelta(minutes=59)):
            assert not TransactionPeriodicCheckService.should_schedule_check_task_immediately(
                trx.id, trx.extra
            )
            trx.refresh_from_db()
            assert trx.extra == {
                "count_status_checks_scheduled": 50,
                "last_status_check_schedule": 1755129960.0,
            }

        with freeze_time(last_schedule + timedelta(minutes=61)):
            assert (
                TransactionPeriodicCheckService.should_schedule_check_task_immediately(
                    trx.id, trx.extra
                )
            )
            trx.refresh_from_db()
            assert trx.extra == {
                "count_status_checks_scheduled": 51,
                "last_status_check_schedule": 1755133620.0,
            }


@patch("rozert_pay.payment.services.transaction_processing.BalanceUpdateService")
class TestTransactionProcessingFunctions:
    def test_handle_chargeback(self, mock_balance_service: MagicMock):
        customer = CustomerFactory.create()
        trx = PaymentTransactionFactory.create(
            status=TransactionStatus.SUCCESS,
            type=TransactionType.DEPOSIT,
            customer=customer,
        )

        with transaction.atomic():
            locked_trx = db_services.get_transaction(trx_id=trx.id, for_update=True)
            transaction_processing.handle_chargeback(locked_trx)

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.CHARGED_BACK
        assert trx.extra["is_chargeback_received"] is True
        assert trx.extra[TransactionExtraFields.IS_CUSTOMER_BLACKLISTED] is True

        blacklist_entry = BlackListEntry.objects.get(transaction=trx)
        assert blacklist_entry.customer == trx.customer
        assert blacklist_entry.merchant == trx.wallet.wallet.merchant
        assert blacklist_entry.transaction == trx
        assert blacklist_entry.scope == Scope.MERCHANT
        assert blacklist_entry.valid_for == ValidFor.PERMANENT
        assert blacklist_entry.reason == Reason.CHARGEBACK

        mock_balance_service.update_balance.assert_called_once()

    def test_handle_refund(self, mock_balance_service: MagicMock):
        trx = PaymentTransactionFactory.create(
            status=TransactionStatus.SUCCESS, type=TransactionType.DEPOSIT
        )
        refund_money = Money(Decimal("30.00"), "USD")

        with transaction.atomic():
            locked_trx = db_services.get_transaction(trx_id=trx.id, for_update=True)
            transaction_processing.handle_refund(locked_trx, refund_money)

        trx.refresh_from_db()
        assert trx.extra["refunded_amount"] == "30.00"

        mock_balance_service.update_balance.assert_called_once()

    def test_handle_chargeback_reversal(self, mock_balance_service: MagicMock):
        trx = PaymentTransactionFactory.create(
            status=TransactionStatus.CHARGED_BACK,
            type=TransactionType.DEPOSIT,
            extra={"is_chargeback_received": True},
        )

        with transaction.atomic():
            locked_trx = db_services.get_transaction(trx_id=trx.id, for_update=True)
            transaction_processing.handle_chargeback_reversal(locked_trx)

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS
        assert trx.extra["is_chargeback_reversal_received"] is True

        mock_balance_service.update_balance.assert_called_once()

    @pytest.mark.parametrize(
        "initial_status, initial_type, should_call_service",
        [
            (TransactionStatus.SUCCESS, TransactionType.DEPOSIT, True),
            (TransactionStatus.SUCCESS, TransactionType.WITHDRAWAL, True),
            (TransactionStatus.FAILED, TransactionType.WITHDRAWAL, True),
            (TransactionStatus.FAILED, TransactionType.DEPOSIT, False),
        ],
    )
    def test_revert_to_pending(
        self,
        mock_balance_service: MagicMock,
        initial_status,
        initial_type,
        should_call_service,
    ):
        trx = PaymentTransactionFactory.create(status=initial_status, type=initial_type)

        transaction_processing.revert_to_pending(trx.id)

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.PENDING

        if should_call_service:
            mock_balance_service.update_balance.assert_called_once()
        else:
            mock_balance_service.update_balance.assert_not_called()
