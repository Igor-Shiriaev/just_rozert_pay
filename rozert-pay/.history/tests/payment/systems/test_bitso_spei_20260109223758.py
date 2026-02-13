import base64
import json
import logging
import re
import typing as ty
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from typing import Callable
from unittest import mock
from unittest.mock import patch

import pytest
import requests_mock
from bm.datatypes import Money
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.contrib import messages
from django.test import Client
from django.utils import timezone
from pytest import mark
from rozert_pay.common import const
from rozert_pay.common.const import PaymentSystemType, TransactionStatus
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import (
    CurrencyWallet,
    CustomerDepositInstruction,
    IncomingCallback,
    OutcomingCallback,
    PaymentCardBank,
    PaymentTransaction,
    PaymentTransactionEventLog,
    Wallet,
)
from rozert_pay.payment.services import wallets_management
from rozert_pay.payment.systems.bitso_spei import bitso_services, bitso_spei_const
from rozert_pay.payment.systems.bitso_spei import tasks as bitso_tasks
from rozert_pay.payment.systems.bitso_spei.audit import BitsoSpeiAudit
from rozert_pay.payment.systems.bitso_spei.bitso_spei_const import (
    BITSO_SPEI_IS_PAYOUT_REFUNDED,
    BITSO_SPEI_PAYOUT_REFUND_DATA,
)
from rozert_pay.payment.systems.bitso_spei.bitso_spei_controller import (
    BitsoSpeiController,
    bitso_spei_controller,
)
from rozert_pay.payment.systems.bitso_spei.client import BitsoSpeiClient
from rozert_pay.payment.systems.bitso_spei.models import (
    BitsoSpeiCardBank,
    BitsoTransactionExtraData,
)
from tests.factories import CurrencyWalletFactory, PaymentTransactionFactory
from tests.payment.systems.fixtures import bitso_spei_fixtures


@mark.django_db
class TestBitsoSpeiAudit:
    @staticmethod
    def _build_remote_deposit(
        *,
        status: str = bitso_spei_const.BITSO_SPEI_STATUS_SUCCESS,
        sender_clabe: str | None = "012180044451188599",
        receiver_clabe: str | None = "710969000012345678",
        overrides: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        now = timezone.now().isoformat()
        deposit: dict[str, object] = {
            "fid": "bitso-fid-1",
            "deposit_id": "bitso-deposit-1",
            "status": status,
            "amount": "120",
            "currency": "mxn",
            "sender_clabe": sender_clabe,
            "receiver_clabe": receiver_clabe,
            "details": {
                "clave_rastreo": "CLAVE123",
                "sender_clabe": sender_clabe,
                "receive_clabe": receiver_clabe,
            },
            "created_at": now,
            "updated_at": now,
        }

        if overrides:
            overrides(deposit)

        return deposit

    @staticmethod
    def _create_audit(
        *, dry_run: bool, start: datetime | None = None, end: datetime | None = None
    ) -> BitsoSpeiAudit:
        return BitsoSpeiAudit(
            start_date=start,
            end_date=end,
            dry_run=dry_run,
        )

    def test_process_deposit_triggers_update_for_success(self, wallet_bitso_spei):
        audit = self._create_audit(dry_run=True)
        deposit = self._build_remote_deposit()
        callback_data = audit._build_callback_data(deposit)
        currency_wallet = CurrencyWalletFactory.create(
            wallet=wallet_bitso_spei, currency="MXN"
        )
        PaymentTransactionFactory.create(
            wallet=currency_wallet,
            system_type=PaymentSystemType.BITSO_SPEI,
            status=TransactionStatus.PENDING,
            id_in_payment_system=deposit["fid"],
        )

        with mock.patch.object(
            audit, "_process_remote_data"
        ) as process_remote_mock:  # pragma: no branch
            audit.process_deposit(callback_data)

        process_remote_mock.assert_called_once_with(
            callback_data, action=BitsoSpeiAudit.ACTION_UPDATE
        )

    def test_process_deposit_triggers_fail_for_failed_status(self, wallet_bitso_spei):
        audit = self._create_audit(dry_run=True)
        deposit = self._build_remote_deposit(status="failed")
        callback_data = audit._build_callback_data(deposit)
        currency_wallet = CurrencyWalletFactory.create(
            wallet=wallet_bitso_spei, currency="MXN"
        )
        PaymentTransactionFactory.create(
            wallet=currency_wallet,
            system_type=PaymentSystemType.BITSO_SPEI,
            status=TransactionStatus.PENDING,
            id_in_payment_system=deposit["fid"],
        )

        with mock.patch.object(audit, "_process_remote_data") as process_remote_mock:
            audit.process_deposit(callback_data)

        process_remote_mock.assert_called_once_with(
            callback_data, action=BitsoSpeiAudit.ACTION_FAIL
        )

    def test_process_deposit_triggers_create_when_transaction_missing(self):
        audit = self._create_audit(dry_run=True)
        callback_data = audit._build_callback_data(self._build_remote_deposit())

        with mock.patch.object(audit, "_process_remote_data") as process_remote_mock:
            audit.process_deposit(callback_data)

        process_remote_mock.assert_called_once_with(
            callback_data, action=BitsoSpeiAudit.ACTION_CREATE
        )

    def test_process_deposit_skips_refund_without_sender_clabe(self, monkeypatch):
        audit = self._create_audit(dry_run=True)
        deposit_data = self._build_remote_deposit(sender_clabe=None)
        monkeypatch.setattr(audit, "_fetch_remote_deposits", lambda: [deposit_data])

        assert list(audit.fetch_bitso_deposits()) == []

    def test_process_remote_data_dry_run_skips(self, monkeypatch):
        audit = self._create_audit(dry_run=True)
        callback_data = audit._build_callback_data(self._build_remote_deposit())

        callback_mock = mock.Mock()
        sync_mock = mock.Mock()
        monkeypatch.setattr(bitso_spei_controller, "callback_logic", callback_mock)
        monkeypatch.setattr(
            bitso_spei_controller,
            "sync_remote_status_with_transaction",
            sync_mock,
        )

        audit._process_remote_data(callback_data, action=BitsoSpeiAudit.ACTION_CREATE)

        callback_mock.assert_not_called()
        sync_mock.assert_not_called()

    def test_process_remote_data_invokes_controller(
        self, monkeypatch, wallet_bitso_spei
    ):
        audit = self._create_audit(dry_run=False)
        remote_deposit = self._build_remote_deposit()
        callback_data = audit._build_callback_data(remote_deposit)

        currency_wallet = CurrencyWalletFactory.create(
            wallet=wallet_bitso_spei, currency="MXN"
        )
        trx = PaymentTransactionFactory.create(
            wallet=currency_wallet,
            system_type=PaymentSystemType.BITSO_SPEI,
            status=TransactionStatus.PENDING,
        )

        remote_status = RemoteTransactionStatus(
            operation_status=TransactionStatus.SUCCESS,
            raw_data={"note": "audit"},
            transaction_id=trx.id,
            id_in_payment_system=ty.cast(str, remote_deposit["fid"]),
            remote_amount=Money(
                callback_data.payload.amount,
                callback_data.payload.currency.upper(),
            ),
        )

        callback_mock = mock.Mock(return_value=remote_status)
        sync_mock = mock.Mock()
        monkeypatch.setattr(
            bitso_spei_controller,
            "callback_logic",
            callback_mock,
        )
        monkeypatch.setattr(
            bitso_spei_controller,
            "sync_remote_status_with_transaction",
            sync_mock,
        )

        audit._process_remote_data(callback_data, action=BitsoSpeiAudit.ACTION_CREATE)

        callback_mock.assert_called_once()
        assert "callback_data" in callback_mock.call_args.kwargs
        processed_callback_data = callback_mock.call_args.kwargs["callback_data"]
        assert (
            processed_callback_data.payload.details.sender_clabe
            == remote_deposit["sender_clabe"]
        )
        sync_mock.assert_called_once_with(
            trx_id=remote_status.transaction_id, remote_status=remote_status
        )


@pytest.fixture
def mock_bitso_signature():
    with patch.object(
        BitsoSpeiController, "_is_callback_signature_valid", return_value=True
    ):
        yield


@mark.django_db
class TestBitsoSpeiFlow:
    def test_deposit_new(
        self,
        merchant_client,
        merchant,
        wallet_bitso_spei,
        mock_send_callback,
        mock_bitso_signature,
    ):
        with (requests_mock.Mocker() as m,):
            m.post(
                "https://bitsospei/spei/v1/clabes",
                json=bitso_spei_fixtures.BITSO_SPEI_GET_CLABE1_SUCCESS_RESPONSE,
            )
            m.get(
                "https://bitsospei/api/v3/fundings/c5b8d7f0768ee91d3b33bee648318688",
                json=bitso_spei_fixtures.BITSO_SPEI_DEPOSIT_GET_STATUS_SUCCESS_RESPONSE,
            )

            # Create instruction
            resp = merchant_client.post(
                "/api/payment/v1/bitso-spei/create_instruction/",
                {
                    "wallet_id": wallet_bitso_spei.uuid,
                    "customer_id": "customer1",
                },
            )
            assert resp.status_code == 200
            assert resp.json() == {
                "customer_id": mock.ANY,
                "deposit_account": bitso_spei_fixtures.CLABE1,
            }

            resp = merchant_client.post(
                "/api/payment/v1/bitso-spei/create_instruction/",
                {
                    "wallet_id": wallet_bitso_spei.uuid,
                    "customer_id": "customer1",
                },
            )

            assert resp.status_code == 200
            assert resp.json() == {
                "customer_id": mock.ANY,
                "deposit_account": bitso_spei_fixtures.CLABE1,
            }

            customer_instruction: CustomerDepositInstruction = (
                CustomerDepositInstruction.objects.get()
            )
            assert customer_instruction.customer.external_id == "customer1"
            assert customer_instruction.wallet == wallet_bitso_spei
            assert (
                customer_instruction.deposit_account_number
                == bitso_spei_fixtures.CLABE1
            )

            _send_callback(
                client=merchant_client,
                payload=bitso_spei_fixtures.BITSO_SPEI_DEPOSIT_SUCCESS_CALLBACK,
                get_status_resp=bitso_spei_fixtures.BITSO_SPEI_DEPOSIT_SUCCESS_CALLBACK,
            )
            assert PaymentTransaction.objects.count() == 1

        trx = PaymentTransaction.objects.get()
        assert trx.customer == customer_instruction.customer
        assert trx.amount == bitso_spei_fixtures.AMOUNT_FOREIGN
        assert trx.currency == bitso_spei_fixtures.CURRENCY_FOREIGN
        assert trx.status == TransactionStatus.SUCCESS
        # TODO: uncomment?
        # assert trx.customer_instruction == customer_instruction

        assert trx.customer_external_account
        assert (
            trx.customer_external_account.unique_account_number
            == bitso_spei_fixtures.SENDER_CLABE
        )
        assert trx.id_in_payment_system == bitso_spei_fixtures.FOREIGN_ID

        assert OutcomingCallback.objects.count() == 1
        cb = OutcomingCallback.objects.get()
        assert cb.body["external_account_id"] == bitso_spei_fixtures.SENDER_CLABE

    def test_withdrawal_success_and_refund(
        self,
        merchant_client,
        merchant,
        wallet_bitso_spei,
        mock_send_callback,
        disable_error_logs,
        mock_bitso_signature,
    ):
        _create_deposit(merchant_client, wallet_bitso_spei)

        currency_wallet = CurrencyWallet.objects.get()
        assert currency_wallet.operational_balance == Decimal("120.00")

        withdrawal_trx = _create_withdrawal(
            merchant_client, wallet_bitso_spei, bitso_spei_fixtures.SENDER_CLABE
        )

        assert withdrawal_trx.status == TransactionStatus.SUCCESS
        # assert withdrawal_trx.extra[TransactionExtraFields.CLAVE_RASTREO] == CLAVE_RASTREO
        assert withdrawal_trx.id_in_payment_system == bitso_spei_fixtures.FOREIGN_ID2

    def test_withdrawal_use_debit_card(
        self,
        merchant_client: Client,
        merchant,
        customer,
        wallet_bitso_spei: Wallet,
        mock_send_callback,
        mock_check_status_task,
        mock_existent_bitso_spei_bank: BitsoSpeiCardBank,
        mock_payment_card_banks: list[PaymentCardBank],
        mock_bitso_signature,
    ):
        # mock_existent_bitso_spei_bank.banks.add(mock_payment_card_banks[0])
        _create_deposit(merchant_client, wallet_bitso_spei)

        currency_wallet = CurrencyWallet.objects.get()
        assert currency_wallet.operational_balance == Decimal("120.00")

        with mock.patch.object(BitsoSpeiClient, "_make_response") as mock_make_response:
            mock_make_response.return_value = (
                bitso_spei_fixtures.BITSO_SPEI_INIT_WITHDRAWAL_PENDING_RESPONSE
            )
            merchant_client.post(
                "/api/payment/v1/bitso-spei/withdraw/",
                {
                    "wallet_id": wallet_bitso_spei.uuid,
                    "amount": 100,
                    "currency": "MXN",
                    "withdraw_to_account": bitso_spei_fixtures.SENDER_CLABE_DEBIT_CARD,
                    "user_data": {
                        "first_name": "test",
                        "last_name": "test",
                    },
                    "customer_id": customer.external_id,
                },
                format="json",
            )
            assert mock_make_response.call_count == 0
            assert (
                PaymentTransactionEventLog.objects.get(
                    extra__clabe=bitso_spei_fixtures.SENDER_CLABE_DEBIT_CARD
                ).description
                == "No BitsoSpeiCardBank found for bin"
            )

            # Add BitsoSpeiCardBank for bin
            mock_existent_bitso_spei_bank.banks.add(mock_payment_card_banks[0])
            merchant_client.post(
                "/api/payment/v1/bitso-spei/withdraw/",
                {
                    "wallet_id": wallet_bitso_spei.uuid,
                    "amount": 100,
                    "currency": "MXN",
                    "withdraw_to_account": bitso_spei_fixtures.SENDER_CLABE_DEBIT_CARD,
                    "user_data": {
                        "first_name": "test",
                        "last_name": "test",
                    },
                },
                format="json",
            )
            assert mock_make_response.call_count == 1
            assert (
                mock_make_response.call_args[1]["json_payload"]["protocol"]
                == "debitcard"
            )
            assert (
                mock_make_response.call_args[1]["json_payload"]["clabe"]
                == bitso_spei_fixtures.SENDER_CLABE_DEBIT_CARD
            )
            assert (
                mock_make_response.call_args[1]["json_payload"]["name"] == "Debit card"
            )
            assert (
                mock_make_response.call_args[1]["json_payload"]["method_name"]
                == "Debit card"
            )
            assert (
                mock_make_response.call_args[1]["json_payload"]["institution_code"]
                == "40012"
            )

    def test_refunded_payout_status_is_failed_even_if_response_says_success(
        self, wallet_bitso_spei
    ):
        trx: PaymentTransaction = PaymentTransactionFactory.create(
            wallet__wallet=wallet_bitso_spei,
            type=const.TransactionType.WITHDRAWAL,
        )
        BitsoTransactionExtraData.objects.create(
            clave_rastreo=bitso_spei_fixtures.CLAVE_RASTREO,
            transaction=trx,
        )
        with requests_mock.Mocker() as m:
            m.get(
                re.compile(r"https://bitsospei/api/v3/withdrawals\?origin_ids=.*"),
                json=bitso_spei_fixtures.BITSO_SPEI_WITHDRAWAL_GET_STATUS_SUCCESS_RESPONSE,
            )

            client = bitso_spei_controller.get_client(trx)

            assert (
                client.get_transaction_status().operation_status  # type: ignore
                == const.TransactionStatus.SUCCESS
            )

            bitso_services.process_bitso_spei_refund(
                refund_data={
                    "payload": {
                        "details": {
                            "clave_rastreo": bitso_spei_fixtures.CLAVE_RASTREO,
                        }
                    }
                },
            )
            trx.refresh_from_db()

            client = bitso_spei_controller.get_client(trx)
            assert trx.extra[BITSO_SPEI_IS_PAYOUT_REFUNDED]
            assert (
                client.get_transaction_status().operation_status  # type: ignore
                == TransactionStatus.FAILED
            )

    @pytest.mark.parametrize(
        ("callback_payload", "expected_amount", "expected_decline_reason"),
        [
            (
                {
                    "event": "funding",
                    "payload": bitso_spei_fixtures.BITSO_SPEI_FAIL_WITHDRAWAL_COMPENSATION_RESPONSE[
                        "payload"
                    ][
                        0
                    ],
                },
                Decimal("3134.41"),
                (
                    "Excede el límite de abonos permitidos en el mes en la cuenta "
                    "(Exceeds the limit of allowed deposits in a month of the account)"
                ),
            ),
            (
                bitso_spei_fixtures.BITSO_SPEI_FAIL_WITHDRAWAL_COMPENSATION_CALLBACK,
                Decimal(str(bitso_spei_fixtures.AMOUNT_FOREIGN)),
                "Cuenta cancelada (Cancelled Account)",
            ),
        ],
        ids=["limit-of-allowed-deposits", "cancelled-account"],
    )
    def test_fail_withdrawal_compensation_callback(
        self,
        merchant_client: Client,
        wallet_bitso_spei: Wallet,
        mock_send_callback,
        mock_bitso_signature,
        callback_payload: dict[str, ty.Any],
        expected_amount: Decimal,
        expected_decline_reason: str,
    ) -> None:
        currency_wallet, _ = CurrencyWallet.objects.get_or_create(
            wallet=wallet_bitso_spei,
            currency=bitso_spei_fixtures.CURRENCY_FOREIGN,
            defaults={
                "operational_balance": Decimal("5000.00"),
                "frozen_balance": Decimal("5000.00"),
                "pending_balance": Decimal("0.00"),
            },
        )
        trx = PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=expected_amount,
            type=const.TransactionType.WITHDRAWAL,
            currency=bitso_spei_fixtures.CURRENCY_FOREIGN,
            system_type=const.PaymentSystemType.BITSO_SPEI,
            status=TransactionStatus.SUCCESS,
            id_in_payment_system=bitso_spei_fixtures.FOREIGN_ID2,
            extra={"claveRastreo": bitso_spei_fixtures.CLAVE_RASTREO},
        )

        callback_data = deepcopy(callback_payload)

        _send_callback(
            client=merchant_client,
            payload=callback_data,
            get_status_resp=callback_data,
        )

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "FAIL_WITHDRAWAL_COMPENSATION"
        assert trx.decline_reason == expected_decline_reason
        assert trx.extra[BITSO_SPEI_IS_PAYOUT_REFUNDED] is True
        assert (
            trx.extra[BITSO_SPEI_PAYOUT_REFUND_DATA]["payload"]["details"]["concepto"]
            == expected_decline_reason
        )

        remote_status_raw = bitso_spei_controller.get_client(
            trx
        ).get_transaction_status()
        assert isinstance(remote_status_raw, RemoteTransactionStatus)
        remote_status = remote_status_raw
        assert remote_status.operation_status == TransactionStatus.FAILED
        assert (
            remote_status.decline_code
            == const.TransactionDeclineCodes.NO_OPERATION_PERFORMED
        )
        assert remote_status.decline_reason == "Payout refunded"
        assert remote_status.remote_amount is None
        assert "__note__" in remote_status.raw_data

    def test_fail_withdrawal_compensation_callback_after_withdrawal_callback(
        self,
        merchant_client: Client,
        wallet_bitso_spei: Wallet,
        mock_send_callback,
        mock_bitso_signature,
    ) -> None:
        currency_wallet, _ = CurrencyWallet.objects.get_or_create(
            wallet=wallet_bitso_spei,
            currency=bitso_spei_fixtures.CURRENCY_FOREIGN,
            defaults={
                "operational_balance": Decimal("5000.00"),
                "frozen_balance": Decimal("5000.00"),
                "pending_balance": Decimal("0.00"),
            },
        )
        trx = PaymentTransactionFactory.create(
            wallet=currency_wallet,
            amount=Decimal(str(bitso_spei_fixtures.AMOUNT_FOREIGN)),
            type=const.TransactionType.WITHDRAWAL,
            currency=bitso_spei_fixtures.CURRENCY_FOREIGN,
            system_type=const.PaymentSystemType.BITSO_SPEI,
            status=TransactionStatus.PENDING,
            id_in_payment_system=bitso_spei_fixtures.FOREIGN_ID,
            extra={},
        )

        success_payload = deepcopy(
            bitso_spei_fixtures.BITSO_SPEI_WITHDRAWAL_SUCCESS_CALLBACK_1
        )
        _send_callback(
            client=merchant_client,
            payload=success_payload,
            get_status_resp=success_payload,
        )

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS

        refund_payload = deepcopy(
            bitso_spei_fixtures.BITSO_SPEI_FAIL_WITHDRAWAL_COMPENSATION_CALLBACK
        )

        _send_callback(
            client=merchant_client,
            payload=refund_payload,
            get_status_resp=refund_payload,
        )

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "FAIL_WITHDRAWAL_COMPENSATION"
        assert trx.decline_reason == "Cuenta cancelada (Cancelled Account)"
        assert trx.extra[BITSO_SPEI_IS_PAYOUT_REFUNDED] is True
        assert (
            trx.extra[BITSO_SPEI_PAYOUT_REFUND_DATA]["payload"]["details"]["concepto"]
            == "Cuenta cancelada (Cancelled Account)"
        )

        remote_status_raw = bitso_spei_controller.get_client(
            trx
        ).get_transaction_status()
        assert isinstance(remote_status_raw, RemoteTransactionStatus)
        remote_status = remote_status_raw
        assert remote_status.operation_status == TransactionStatus.FAILED
        assert (
            remote_status.decline_code
            == const.TransactionDeclineCodes.NO_OPERATION_PERFORMED
        )
        assert remote_status.decline_reason == "Payout refunded"
        assert remote_status.remote_amount is None
        assert "__note__" in remote_status.raw_data

        assert PaymentTransaction.objects.count() == 1


@mark.django_db
def test_callback_signature_validation_success(wallet_bitso_spei: Wallet) -> None:
    BitsoSpeiController._get_public_key.cache_clear()

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    key_id = "test-key"
    wallet_bitso_spei.credentials.update(
        {
            "public_keys": [
                {
                    "key_id": key_id,
                    "public_key": public_key_pem.decode("utf-8"),
                }
            ]
        }
    )
    wallet_bitso_spei.save(update_fields=["credentials_encrypted", "updated_at"])

    payload = {"foo": "bar", "number": 123}
    payload_bytes = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = private_key.sign(payload_bytes, padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    cb = IncomingCallback.objects.create(
        system=wallet_bitso_spei.system,
        body=json.dumps({"payload": payload}),
        headers={
            "x-bitso-webhook-event-signature": signature_b64,
            "x-bitso-key-id": key_id,
        },
        get_params={},
        ip="127.0.0.1",
    )

    assert bitso_spei_controller._is_callback_signature_valid(cb) is True
    assert cb.error is None


@mark.django_db
def test_callback_signature_validation_invalid_signature(
    wallet_bitso_spei: Wallet,
) -> None:
    BitsoSpeiController._get_public_key.cache_clear()

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    key_id = "test-key"
    wallet_bitso_spei.credentials.update(
        {
            "public_keys": [
                {
                    "key_id": key_id,
                    "public_key": public_key_pem.decode("utf-8"),
                }
            ]
        }
    )
    wallet_bitso_spei.save(update_fields=["credentials_encrypted", "updated_at"])

    payload = {"foo": "bar", "number": 123}
    cb = IncomingCallback.objects.create(
        system=wallet_bitso_spei.system,
        body=json.dumps({"payload": payload}),
        headers={
            "x-bitso-webhook-event-signature": base64.b64encode(b"invalid").decode(
                "utf-8"
            ),
            "x-bitso-key-id": key_id,
        },
        get_params={},
        ip="127.0.0.1",
    )

    assert bitso_spei_controller._is_callback_signature_valid(cb) is False
    assert cb.error == "Bitso signature verification failed"


@mark.django_db
def test_credentials_change_action_updates_webhooks(wallet_bitso_spei: Wallet) -> None:
    old_creds = {**wallet_bitso_spei.credentials}
    new_creds = {**old_creds, "api_key": "new-key", "api_secret": "new-secret"}
    message_calls: list[tuple[str, int]] = []

    def message_user(msg: str, level: int) -> None:
        message_calls.append((msg, level))

    with requests_mock.Mocker() as requests_mocker:
        requests_mocker.get(
            "https://bitsospei/v4/webhooks/",
            [
                {
                    "json": [
                        {
                            "id": 555,
                            "callback_url": "https://api.rozert.cloud/old",
                            "event": "funding",
                        }
                    ]
                },
                {
                    "json": [
                        {
                            "id": 777,
                            "callback_url": "https://callbacks/new",
                            "event": "funding",
                        }
                    ]
                },
            ],
        )
        requests_mocker.delete(
            "https://bitsospei/v4/webhooks/555",
            status_code=204,
        )
        requests_mocker.post(
            "https://bitsospei/v4/webhooks/",
            status_code=201,
            json={},
        )
        requests_mocker.get(
            "https://bitsospei/v4/webhooks/public-key",
            json=[{"key_id": "123"}],
        )

        log_writer = wallets_management.perform_wallet_credentials_change_action(
            controller=bitso_spei_controller,
            wallet=wallet_bitso_spei,
            old_creds=old_creds,
            new_creds=new_creds,
            is_sandbox=False,
            message_user=message_user,
        )
        assert log_writer is not None
        history = list(requests_mocker.request_history)

    wallet_bitso_spei.refresh_from_db()
    assert wallet_bitso_spei.credentials["public_keys"] == [{"key_id": "123"}]
    assert any(
        entry.endswith("Saved public keys to creds") for entry in log_writer.logs
    )
    assert "Removed webhook https://api.rozert.cloud/old" in log_writer.to_string()
    assert message_calls == [
        ("Credentials change action performed successfully", messages.SUCCESS)
    ]

    assert any(
        request.method == "DELETE"
        and request.url == "https://bitsospei/v4/webhooks/555"
        for request in history
    )
    assert any(
        request.method == "POST" and request.url == "https://bitsospei/v4/webhooks/"
        for request in history
    )
    assert any(
        request.method == "GET"
        and request.url == "https://bitsospei/v4/webhooks/public-key"
        for request in history
    )


@mark.django_db
class TestRunBitsoSpeiAuditTask:
    def test_run_bitso_spei_audit_invokes_audit(self, monkeypatch, caplog):
        captured: dict[str, ty.Any] = {}

        class DummyAudit:
            def __init__(
                self,
                *,
                start_date: datetime | None,
                end_date: datetime | None,
                dry_run: bool,
            ):
                captured["start_date"] = start_date
                captured["end_date"] = end_date
                captured["dry_run"] = dry_run

            def run(self) -> None:
                captured["run_called"] = True

        monkeypatch.setattr(bitso_tasks, "BitsoSpeiAudit", DummyAudit)

        caplog.set_level(logging.INFO, logger=bitso_tasks.logger.name)

        bitso_tasks.run_bitso_spei_audit(
            start_date="2025-02-25T13:00:00+00:00",
            end_date="2025-02-25T14:00:00+00:00",
            dry_run=True,
            wallet_ids=[1, 2],
            initiated_by=42,
        )

        assert captured["run_called"] is True
        assert captured["dry_run"] is True
        assert captured["start_date"].isoformat() == "2025-02-25T13:00:00+00:00"
        assert captured["end_date"].isoformat() == "2025-02-25T14:00:00+00:00"
        assert "Bitso SPEI audit scheduled" in caplog.text

    def test_run_bitso_spei_audit_defaults(self, monkeypatch, caplog):
        captured: dict[str, ty.Any] = {}

        class DummyAudit:
            def __init__(
                self,
                *,
                start_date: datetime | None,
                end_date: datetime | None,
                dry_run: bool,
            ):
                captured["start_date"] = start_date
                captured["end_date"] = end_date
                captured["dry_run"] = dry_run

            def run(self) -> None:
                captured["run_called"] = True

        monkeypatch.setattr(bitso_tasks, "BitsoSpeiAudit", DummyAudit)

        caplog.set_level(logging.INFO, logger=bitso_tasks.logger.name)

        bitso_tasks.run_bitso_spei_audit()

        assert captured["run_called"] is True
        assert captured["start_date"] is None
        assert captured["end_date"] is None
        assert captured["dry_run"] is False
        assert "Bitso SPEI audit scheduled" in caplog.text


def _send_callback(
    client: Client, payload: dict[str, ty.Any], get_status_resp: dict[str, ty.Any]
) -> None:
    resp = client.post(
        "/api/payment/v1/callback/bitso-spei/",
        data=payload,
        format="json",
    )
    assert resp.status_code == 200


def _create_deposit(
    merchant_client: Client,
    wallet_bitso_spei: Wallet,
) -> PaymentTransaction:
    with requests_mock.Mocker() as m:
        m.post(
            "https://bitsospei/spei/v1/clabes",
            json=bitso_spei_fixtures.BITSO_SPEI_GET_CLABE1_SUCCESS_RESPONSE,
        )
        m.get(
            "https://bitsospei/api/v3/fundings/c5b8d7f0768ee91d3b33bee648318688",
            json=bitso_spei_fixtures.BITSO_SPEI_DEPOSIT_GET_STATUS_SUCCESS_RESPONSE,
        )

        # Create instruction
        resp = merchant_client.post(
            "/api/payment/v1/bitso-spei/create_instruction/",
            {
                "wallet_id": wallet_bitso_spei.uuid,
                "customer_id": "customer1",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "customer_id": mock.ANY,
            "deposit_account": bitso_spei_fixtures.CLABE1,
        }

        resp = merchant_client.post(
            "/api/payment/v1/bitso-spei/create_instruction/",
            {
                "wallet_id": wallet_bitso_spei.uuid,
                "customer_id": "customer1",
            },
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "customer_id": mock.ANY,
            "deposit_account": bitso_spei_fixtures.CLABE1,
        }

        customer_instruction: CustomerDepositInstruction = (
            CustomerDepositInstruction.objects.get()
        )
        assert customer_instruction.customer.external_id == "customer1"
        assert customer_instruction.wallet == wallet_bitso_spei
        assert customer_instruction.deposit_account_number == bitso_spei_fixtures.CLABE1

        _send_callback(
            client=merchant_client,
            payload=bitso_spei_fixtures.BITSO_SPEI_DEPOSIT_SUCCESS_CALLBACK,
            get_status_resp=bitso_spei_fixtures.BITSO_SPEI_DEPOSIT_SUCCESS_CALLBACK,
        )
        assert PaymentTransaction.objects.count() == 1

        return PaymentTransaction.objects.get()


def _create_withdrawal(
    merchant_client: Client,
    wallet_bitso_spei: Wallet,
    clabe: str = bitso_spei_fixtures.SENDER_CLABE,
) -> PaymentTransaction:
    with requests_mock.Mocker() as m:
        m.post(
            "https://bitsospei/api/v3/withdrawals",
            json=bitso_spei_fixtures.BITSO_SPEI_INIT_WITHDRAWAL_PENDING_RESPONSE,
        )
        m.get(
            re.compile(r"https://bitsospei/api/v3/withdrawals\?origin_ids=.*"),
            json=bitso_spei_fixtures.BITSO_SPEI_WITHDRAWAL_GET_STATUS_SUCCESS_RESPONSE,
        )

        resp = merchant_client.post(
            "/api/payment/v1/bitso-spei/withdraw/",
            {
                "wallet_id": wallet_bitso_spei.uuid,
                "amount": 100,
                "currency": "MXN",
                "withdraw_to_account": clabe,
                "user_data": {
                    "first_name": "test",
                    "last_name": "test",
                },
            },
            format="json",
        )
        assert resp.status_code == 201

        withdrawal_trx = PaymentTransaction.objects.last()
        assert withdrawal_trx
        return withdrawal_trx
