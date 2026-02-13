from datetime import timedelta
from unittest import mock
from unittest.mock import patch

import pytest
import requests_mock
from bm.datatypes import Money
from django.utils import timezone
from freezegun import freeze_time
from rozert_pay.common import const
from rozert_pay.common.const import CallbackStatus, TransactionStatus
from rozert_pay.payment import tasks
from rozert_pay.payment.models import OutcomingCallback, PaymentTransaction
from rozert_pay.payment.systems.paycash import PaycashClient
from rozert_pay.payment.tasks import check_status
from tests.factories import PaymentTransactionFactory, RemoteTransactionStatusFactory
from tests.payment.api_v1 import matchers


@pytest.mark.django_db
class TestTasks:
    def test_task_fail_by_timeout(
        self, wallet_spei, django_capture_on_commit_callbacks
    ):
        now = timezone.now()
        with freeze_time(now - timedelta(minutes=16)):
            trx = PaymentTransactionFactory.create(wallet__wallet=wallet_spei)

        with requests_mock.Mocker() as m, django_capture_on_commit_callbacks(
            execute=True
        ):
            m.post(
                "http://callback/",
                json={
                    "key": "value",
                },
            )
            tasks.task_fail_by_timeout(
                transaction_id=trx.id,
                ttl_seconds=15 * 60,
            )

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.FAILED
        assert OutcomingCallback.objects.count() == 1
        cb: OutcomingCallback | None = OutcomingCallback.objects.first()
        assert cb
        assert cb.transaction == trx
        assert cb.status == CallbackStatus.SUCCESS
        assert cb.body == matchers.DictContains(
            {
                "amount": "100.00",
                "currency": "USD",
                "customer_id": None,
                "card_token": None,
                "id": mock.ANY,
                "status": "failed",
                "type": "deposit",
                "wallet_id": mock.ANY,
                "decline_code": "USER_HAS_NOT_FINISHED_FLOW",
                "decline_reason": "Too long execution for transaction",
                "created_at": mock.ANY,
                "updated_at": mock.ANY,
            }
        )

    @pytest.fixture
    def mocks_check_pending_transaction_status(self):
        self.now = timezone.now()
        with (
            patch.object(
                check_status, "delay", wraps=check_status.delay
            ) as self.delay_mck,
            freeze_time(self.now),
            patch.object(
                PaycashClient,
                "get_transaction_status",
                return_value=RemoteTransactionStatusFactory(),
            ) as self.status_mck,
        ):
            yield

    def test_check_pending_transaction_status_expired_withdrawal(
        self, mocks_check_pending_transaction_status
    ):
        trx: PaymentTransaction = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.WITHDRAWAL,
            check_status_until=self.now - timedelta(minutes=1),
        )

        tasks.check_pending_transaction_status()
        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.PENDING
        assert trx.paymenttransactioneventlog_set.count() == 1

    def test_check_pending_transaction_status_expired_deposit(
        self, mocks_check_pending_transaction_status
    ):
        trx = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=const.TransactionType.DEPOSIT,
            check_status_until=self.now - timedelta(minutes=1),
        )

        tasks.check_pending_transaction_status()
        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.FAILED
        assert (
            trx.decline_code
            == const.TransactionDeclineCodes.DEPOSIT_NOT_PROCESSED_IN_TIME
        )

    @pytest.mark.parametrize(
        "type", [const.TransactionType.WITHDRAWAL, const.TransactionType.DEPOSIT]
    )
    def test_check_pending_transaction_status_success(
        self, mocks_check_pending_transaction_status, type
    ):
        trx = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=type,
            check_status_until=self.now + timedelta(minutes=1),
            wallet__hold_balance=100,
        )
        self.status_mck.return_value.operation_status = const.TransactionStatus.SUCCESS
        self.status_mck.return_value.remote_amount = Money(trx.amount, trx.currency)

        tasks.check_pending_transaction_status()

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.SUCCESS

    @pytest.mark.parametrize(
        "type", [const.TransactionType.WITHDRAWAL, const.TransactionType.DEPOSIT]
    )
    def test_check_pending_transaction_status_fail(
        self, mocks_check_pending_transaction_status, type
    ):
        trx = PaymentTransactionFactory.create(
            status=const.TransactionStatus.PENDING,
            type=type,
            check_status_until=self.now + timedelta(minutes=1),
            wallet__hold_balance=100,
        )
        self.status_mck.return_value.operation_status = const.TransactionStatus.FAILED
        self.status_mck.return_value.decline_code = "123"
        self.status_mck.return_value.remote_amount = Money(trx.amount, trx.currency)

        tasks.check_pending_transaction_status()

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.FAILED
        assert trx.decline_code == "123"
