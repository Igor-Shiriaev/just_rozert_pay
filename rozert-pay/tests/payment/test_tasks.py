import logging
from datetime import timedelta
from unittest import mock
from unittest.mock import Mock, patch

import pytest
import requests_mock
from bm.datatypes import Money
from django.utils import timezone
from freezegun import freeze_time
from rozert_pay.common import const
from rozert_pay.common.const import CallbackStatus, EventType, TransactionStatus
from rozert_pay.payment import tasks
from rozert_pay.payment.models import (
    OutcomingCallback,
    PaymentCardBank,
    PaymentTransaction,
)
from rozert_pay.payment.systems.bitso_spei.models import BitsoSpeiCardBank
from rozert_pay.payment.systems.paycash import PaycashClient
from rozert_pay.payment.tasks import check_bitso_spei_bank_codes, check_status
from tests.factories import (
    PaymentTransactionEventLogFactory,
    PaymentTransactionFactory,
    RemoteTransactionStatusFactory,
)
from tests.payment.api_v1 import matchers


@pytest.mark.django_db
class TestTasks:
    def test_task_fail_by_timeout(
        self, wallet_spei, django_capture_on_commit_callbacks
    ):
        now = timezone.now()
        with freeze_time(now - timedelta(minutes=16)):
            trx = PaymentTransactionFactory.create(wallet__wallet=wallet_spei)

        with (
            requests_mock.Mocker() as m,
            django_capture_on_commit_callbacks(execute=True),
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

    def test_task_periodic_fail_old_transactions(self, wallet_spei, caplog):
        now = timezone.now()
        very_old = now - timedelta(days=300)

        payout_trx: PaymentTransaction = PaymentTransactionFactory.create(
            type=const.TransactionType.WITHDRAWAL,
            status=const.TransactionStatus.PENDING,
        )
        payout_trx.created_at = very_old
        payout_trx.save()

        deposit_trx_old: PaymentTransaction = PaymentTransactionFactory.create(
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        deposit_trx_old.created_at = very_old
        deposit_trx_old.save()

        assert wallet_spei.system.deposit_allowed_ttl_seconds == 172800
        deposit_pending: PaymentTransaction = PaymentTransactionFactory.create(
            type=const.TransactionType.DEPOSIT,
            status=const.TransactionStatus.PENDING,
        )
        deposit_pending.created_at = now - timedelta(hours=47)
        deposit_pending.save()

        tasks.task_periodic_fail_old_transactions()

        payout_trx.refresh_from_db()
        assert payout_trx.status == const.TransactionStatus.PENDING

        deposit_trx_old.refresh_from_db()
        assert deposit_trx_old.status == const.TransactionStatus.FAILED
        assert deposit_trx_old.decline_code == "USER_HAS_NOT_FINISHED_FLOW"
        assert deposit_trx_old.decline_reason == "Too long execution for transaction"

        deposit_pending.refresh_from_db()
        assert deposit_pending.status == const.TransactionStatus.PENDING

        for r in caplog.record_tuples:
            assert r[1] < logging.ERROR, r

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
            wallet__frozen_balance=100,
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
            wallet__frozen_balance=100,
        )
        self.status_mck.return_value.operation_status = const.TransactionStatus.FAILED
        self.status_mck.return_value.decline_code = "123"
        self.status_mck.return_value.remote_amount = Money(trx.amount, trx.currency)

        tasks.check_pending_transaction_status()

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.FAILED
        assert trx.decline_code == "123"


@pytest.mark.django_db
class TestCheckBitsoSpeiBankCodes:
    """Test suite for check_bitso_spei_bank_codes task."""

    def test_successful_api_response_with_matching_banks(
        self,
        mock_bitso_api_response: requests_mock.Mocker,
        mock_payment_card_banks: list[PaymentCardBank],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.INFO):
            check_bitso_spei_bank_codes()

        assert mock_bitso_api_response.call_count == 1
        assert BitsoSpeiCardBank.objects.count() == 3

        banorte_bank = BitsoSpeiCardBank.objects.get(code="40072")
        assert banorte_bank.name == "BANORTE"
        assert banorte_bank.country_code == "MX"
        assert banorte_bank.is_active is True
        assert banorte_bank.banks.count() == 1  # Should find matching PaymentCardBank

        covalto_bank = BitsoSpeiCardBank.objects.get(code="40154")
        assert covalto_bank.name == "BANCO COVALTO"
        assert covalto_bank.country_code == "MX"
        assert covalto_bank.is_active is True
        assert covalto_bank.banks.count() == 1  # Should find matching PaymentCardBank

        bank_of_america_bank = BitsoSpeiCardBank.objects.get(code="40106")
        assert bank_of_america_bank.name == "BANK OF AMERICA"
        assert bank_of_america_bank.country_code == "MX"
        assert bank_of_america_bank.is_active is True
        assert (
            bank_of_america_bank.banks.count() == 1
        )  # Should find matching PaymentCardBank

        assert "Successfully processed Bitso banks and BIN relations" in caplog.text
        assert "Linked PaymentCardBank to BitsoSpeiCardBank" in caplog.text

    def test_api_response_with_success_false(
        self,
        mock_bitso_api_response: requests_mock.Mocker,
        caplog: pytest.LogCaptureFixture,
        disable_error_logs,
    ) -> None:
        """Test handling of API response with success=False."""
        mock_bitso_api_response.get(
            "https://bitso.com/api/v3/banks/MX",
            json={
                "success": False,
                "error": "Some error message",
            },
        )

        with caplog.at_level(logging.ERROR):
            check_bitso_spei_bank_codes()

        assert mock_bitso_api_response.call_count == 1
        assert BitsoSpeiCardBank.objects.count() == 0
        assert "Bitso API returned unsuccessful response" in caplog.text

    def test_update_existing_bank(
        self,
        mock_bitso_api_response: requests_mock.Mocker,
        mock_existent_bitso_spei_bank: BitsoSpeiCardBank,
    ) -> None:
        existing_bank = mock_existent_bitso_spei_bank
        assert existing_bank.code == "40012"

        mock_bitso_api_response.get(
            "https://bitso.com/api/v3/banks/MX",
            json={
                "success": True,
                "payload": [
                    {
                        "code": "228",
                        "name": "BBVA Bancomer",
                        "countryCode": "MX",
                        "isActive": True,
                    },
                ],
            },
        )

        check_bitso_spei_bank_codes()

        existing_bank.refresh_from_db()
        assert existing_bank.code == "228"
        assert existing_bank.name == "BBVA Bancomer"
        assert existing_bank.country_code == "MX"
        assert existing_bank.is_active is True

    @patch("rozert_pay.payment.tasks.requests.get")
    def test_general_exception_handling(
        self,
        mock_get: Mock,
        caplog: pytest.LogCaptureFixture,
        disable_error_logs,
    ) -> None:
        """Test handling of general exceptions in the main process."""
        mock_get.side_effect = Exception("Unexpected error")

        with caplog.at_level(logging.ERROR):
            check_bitso_spei_bank_codes()

        mock_get.assert_called_once()
        assert "Error processing Bitso banks" in caplog.text


@pytest.mark.django_db
class TestCleanupDuplicateLogsTask:
    """
    Tests for the cleanup_duplicate_logs task, focusing on the default
    behavior (sliding window) used by Celery Beat.
    """

    def test_cleanup(self):
        old: PaymentTransaction = PaymentTransactionFactory.create()

        extra = {"response": {"text": {"a": "123"}}}
        PaymentTransactionEventLogFactory.create(
            transaction=old,
            event_type=EventType.EXTERNAL_API_REQUEST,
            extra=extra,
            description="descr",
        )
        PaymentTransactionEventLogFactory.create(
            transaction=old,
            event_type=EventType.EXTERNAL_API_REQUEST,
            extra=extra,
            description="descr",
        )

        new: PaymentTransaction = PaymentTransactionFactory.create()
        PaymentTransactionEventLogFactory.create(
            transaction=new,
            event_type=EventType.EXTERNAL_API_REQUEST,
            extra=extra,
            description="descr",
        )
        PaymentTransactionEventLogFactory.create(
            transaction=new,
            event_type=EventType.EXTERNAL_API_REQUEST,
            extra=extra,
            description="descr",
        )
        PaymentTransactionEventLogFactory.create(
            transaction=new,
            event_type=EventType.INFO,
            extra=extra,
            description="descr",
        )
        PaymentTransaction.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(days=10)
        )

        assert new.paymenttransactioneventlog_set.count() == 3

        tasks.task_periodic_cleanup_duplicate_logs()

        assert new.paymenttransactioneventlog_set.count() == 2
        assert old.paymenttransactioneventlog_set.count() == 2

        tasks.task_periodic_cleanup_duplicate_logs(full_cleanup=True)

        assert new.paymenttransactioneventlog_set.count() == 2
        assert old.paymenttransactioneventlog_set.count() == 1
