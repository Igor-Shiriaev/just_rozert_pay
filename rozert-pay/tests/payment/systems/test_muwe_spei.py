import typing as ty
import uuid
from decimal import Decimal
from unittest import mock

import requests_mock
from django.test import Client
from pytest import mark
from rozert_pay.common.const import (
    IncomingCallbackError,
    TransactionStatus,
    TransactionType,
)
from rozert_pay.limits.const import SLACK_PS_STATUS_CHANNEL
from rozert_pay.payment.models import (
    CustomerDepositInstruction,
    IncomingCallback,
    OutcomingCallback,
    PaymentTransaction,
)
from rozert_pay.payment.services.base_classes import RemoteTransactionStatus
from rozert_pay.payment.systems.muwe_spei import muwe_spei_helpers
from rozert_pay.payment.systems.muwe_spei.client import MuweSpeiClient
from rozert_pay.payment.systems.muwe_spei.muwe_spei_const import (
    BANK_CODE_EXTRA_KEY,
    MUWE_SPEI_IDENTIFIER,
    MUWE_SPEI_MCH_ORDER_NO,
)
from tests.factories import MuweSpeiBankFactory, PaymentTransactionFactory
from tests.payment.systems.fixtures import muwe_spei_fixtures


@mark.django_db
@mark.usefixtures("disable_cache")
class TestMuweSpeiFlow:
    def test_deposit_new(
        self,
        merchant_client,
        merchant,
        wallet_muwe_spei,
        mock_send_callback,
    ):
        customer_id = str(uuid.uuid4())
        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/collection/create",
                json=muwe_spei_fixtures.MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE,
            )

            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/create_instruction/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "customer_id": customer_id,
                },
            )
            assert resp.status_code == 200
            assert resp.json() == {
                "customer_id": mock.ANY,
                "deposit_account": muwe_spei_fixtures.CLABE1,
            }

            # Call again - should return the same CLABE (idempotent)
            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/create_instruction/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "customer_id": customer_id,
                },
            )

            assert resp.status_code == 200
            assert resp.json() == {
                "customer_id": mock.ANY,
                "deposit_account": muwe_spei_fixtures.CLABE1,
            }

            customer_instruction: CustomerDepositInstruction = (
                CustomerDepositInstruction.objects.get()
            )
            assert customer_instruction.customer.external_id == customer_id
            assert customer_instruction.wallet == wallet_muwe_spei
            assert (
                customer_instruction.deposit_account_number == muwe_spei_fixtures.CLABE1
            )

            # Send deposit success webhook
            _send_callback(
                client=merchant_client,
                payload=muwe_spei_fixtures.MUWE_DEPOSIT_SUCCESS_WEBHOOK,
            )
            assert PaymentTransaction.objects.count() == 1

        trx = PaymentTransaction.objects.get()
        assert trx.customer == customer_instruction.customer
        assert trx.amount == Decimal(str(muwe_spei_fixtures.AMOUNT))
        assert trx.currency == muwe_spei_fixtures.CURRENCY
        assert trx.status == TransactionStatus.SUCCESS

        assert trx.customer_external_account
        assert (
            trx.customer_external_account.unique_account_number
            == muwe_spei_fixtures.CLABE1
        )
        assert trx.extra[MUWE_SPEI_IDENTIFIER] == muwe_spei_fixtures.IDENTIFIER
        assert trx.id_in_payment_system == muwe_spei_fixtures.FOREIGN_ID_DEPOSIT

        assert OutcomingCallback.objects.count() == 1
        cb = OutcomingCallback.objects.get()
        assert cb.body["external_account_id"] == muwe_spei_fixtures.CLABE1

    def test_withdrawal_success(
        self,
        merchant_client,
        wallet_muwe_spei,
        mock_send_callback,
        mock_check_status_task,
        mock_on_commit,
    ):
        MuweSpeiBankFactory.create(
            code=muwe_spei_fixtures.BANK_CODE,
            name="SANTANDER",
        )
        customer_id = str(uuid.uuid4())

        # First create deposit to have balance
        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/collection/create",
                json=muwe_spei_fixtures.MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE,
            )

            # Create instruction
            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/create_instruction/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "customer_id": customer_id,
                },
            )
            assert resp.status_code == 200

            # Send deposit success webhook
            _send_callback(
                client=merchant_client,
                payload=muwe_spei_fixtures.MUWE_DEPOSIT_SUCCESS_WEBHOOK,
            )

        # Now test withdrawal
        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/agentpay/apply",
                json=muwe_spei_fixtures.MUWE_WITHDRAWAL_INIT_SUCCESS_RESPONSE,
            )

            # Create withdrawal
            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/withdraw/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "amount": 100,
                    "currency": "MXN",
                    "withdraw_to_account": muwe_spei_fixtures.CLABE1,
                    "user_data": {
                        "first_name": "Test",
                        "last_name": "User",
                    },
                    "customer_id": customer_id,
                },
                format="json",
            )
            assert resp.status_code == 201

        # Check withdrawal transaction was created
        withdrawal_trx = PaymentTransaction.objects.filter(type="withdrawal").first()
        assert withdrawal_trx
        assert (
            withdrawal_trx.id_in_payment_system
            == muwe_spei_fixtures.FOREIGN_ID_WITHDRAWAL
        )
        assert withdrawal_trx.status == TransactionStatus.PENDING

        # Send withdrawal success webhook
        withdrawal_webhook = muwe_spei_fixtures.MUWE_WITHDRAWAL_SUCCESS_WEBHOOK.copy()
        withdrawal_webhook[MUWE_SPEI_MCH_ORDER_NO] = str(withdrawal_trx.uuid)
        _send_callback(
            client=merchant_client,
            payload=withdrawal_webhook,
        )

        # Verify withdrawal succeeded
        withdrawal_trx.refresh_from_db()
        assert withdrawal_trx.status == TransactionStatus.SUCCESS
        assert (
            withdrawal_trx.extra[MUWE_SPEI_IDENTIFIER]
            == withdrawal_webhook[MUWE_SPEI_IDENTIFIER]
        )

    def test_withdrawal_determines_bank_code_from_clabe(
        self,
        merchant_client,
        wallet_muwe_spei,
        mock_send_callback,
        mock_check_status_task,
        mock_on_commit,
    ):
        MuweSpeiBankFactory.create(code="90646", name="BANK_646")

        customer_id = str(uuid.uuid4())

        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/collection/create",
                json=muwe_spei_fixtures.MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE,
            )

            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/create_instruction/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "customer_id": customer_id,
                },
            )
            assert resp.status_code == 200

            _send_callback(
                client=merchant_client,
                payload=muwe_spei_fixtures.MUWE_DEPOSIT_SUCCESS_WEBHOOK,
            )

        deposit_trx = PaymentTransaction.objects.get(type=TransactionType.DEPOSIT)
        external_account = deposit_trx.customer_external_account
        assert external_account
        del external_account.extra[BANK_CODE_EXTRA_KEY]
        external_account.save()

        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/agentpay/apply",
                json=muwe_spei_fixtures.MUWE_WITHDRAWAL_INIT_SUCCESS_RESPONSE,
            )

            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/withdraw/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "amount": 100,
                    "currency": "MXN",
                    "withdraw_to_account": muwe_spei_fixtures.CLABE1,
                    "user_data": {
                        "first_name": "Test",
                        "last_name": "User",
                    },
                    "customer_id": customer_id,
                },
                format="json",
            )
            assert resp.status_code == 201

        withdrawal_trx = PaymentTransaction.objects.filter(type="withdrawal").first()
        assert withdrawal_trx
        assert withdrawal_trx.status == TransactionStatus.PENDING

    def test_deposit_failed(
        self,
        merchant_client,
        wallet_muwe_spei,
        mock_send_callback,
        mock_on_commit,
    ):
        customer_id = str(uuid.uuid4())
        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/collection/create",
                json=muwe_spei_fixtures.MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE,
            )

            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/create_instruction/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "customer_id": customer_id,
                },
            )
            assert resp.status_code == 200

            _send_callback(
                client=merchant_client,
                payload=muwe_spei_fixtures.MUWE_DEPOSIT_FAILED_WEBHOOK,
            )

        assert PaymentTransaction.objects.count() == 1
        trx = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.FAILED
        assert (
            trx.decline_code
            == muwe_spei_fixtures.MUWE_DEPOSIT_FAILED_WEBHOOK["errCode"]
        )
        assert (
            trx.decline_reason
            == muwe_spei_fixtures.MUWE_DEPOSIT_FAILED_WEBHOOK["errMsg"]
        )

        assert (
            trx.id_in_payment_system
            == muwe_spei_fixtures.MUWE_DEPOSIT_FAILED_WEBHOOK["orderId"]
        )

        assert OutcomingCallback.objects.count() == 1

    def test_deposit_determines_bank_code_from_clabe(
        self,
        merchant_client,
        wallet_muwe_spei,
        mock_send_callback,
    ):
        MuweSpeiBankFactory.create(code="40002", name="BANAMEX")

        customer_id = str(uuid.uuid4())
        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/collection/create",
                json=muwe_spei_fixtures.MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE,
            )

            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/create_instruction/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "customer_id": customer_id,
                },
            )
            assert resp.status_code == 200

            _send_callback(
                client=merchant_client,
                payload=muwe_spei_fixtures.MUWE_DEPOSIT_SUCCESS_WEBHOOK_NO_BANK_CODE,
            )

        assert PaymentTransaction.objects.count() == 1
        trx = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.SUCCESS

        assert trx.customer_external_account
        assert trx.customer_external_account.extra[BANK_CODE_EXTRA_KEY] == "40002"

    def test_deposit_fails_when_no_bank_code_and_no_matching_bank(
        self,
        merchant_client,
        wallet_muwe_spei,
        mock_send_callback,
        disable_error_logs,
    ):
        customer_id = str(uuid.uuid4())
        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/collection/create",
                json=muwe_spei_fixtures.MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE,
            )

            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/create_instruction/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "customer_id": customer_id,
                },
            )
            assert resp.status_code == 200

            _send_callback(
                client=merchant_client,
                payload=muwe_spei_fixtures.MUWE_DEPOSIT_SUCCESS_WEBHOOK_NO_BANK_CODE,
            )

        cb = IncomingCallback.objects.get()
        assert cb.error_type == IncomingCallbackError.UNKNOWN_ERROR
        assert cb.error is not None
        assert "Could not determine bankCode" in cb.error

    def test_withdrawal_failed(
        self,
        merchant_client,
        wallet_muwe_spei,
        mock_send_callback,
        mock_check_status_task,
        mock_on_commit,
    ):
        customer_id = str(uuid.uuid4())
        MuweSpeiBankFactory.create(
            code=muwe_spei_fixtures.BANK_CODE,
            name="SANTANDER",
        )

        # First create deposit to have balance and external account
        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/collection/create",
                json=muwe_spei_fixtures.MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE,
            )

            # Create instruction
            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/create_instruction/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "customer_id": customer_id,
                },
            )
            assert resp.status_code == 200

            # Send deposit success webhook
            _send_callback(
                client=merchant_client,
                payload=muwe_spei_fixtures.MUWE_DEPOSIT_SUCCESS_WEBHOOK,
            )

        # Now test withdrawal
        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/agentpay/apply",
                json=muwe_spei_fixtures.MUWE_WITHDRAWAL_INIT_SUCCESS_RESPONSE,
            )

            # Create withdrawal
            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/withdraw/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "amount": 100,
                    "currency": "MXN",
                    "withdraw_to_account": muwe_spei_fixtures.CLABE1,
                    "user_data": {
                        "first_name": "Test",
                        "last_name": "User",
                    },
                    "customer_id": customer_id,
                },
                format="json",
            )
            assert resp.status_code == 201

        # Get withdrawal transaction
        withdrawal_trx = PaymentTransaction.objects.filter(type="withdrawal").first()
        assert withdrawal_trx
        assert withdrawal_trx.status == TransactionStatus.PENDING

        # Send withdrawal failed webhook
        withdrawal_webhook = muwe_spei_fixtures.MUWE_WITHDRAWAL_FAILED_WEBHOOK.copy()
        withdrawal_webhook["mchOrderNo"] = str(withdrawal_trx.uuid)
        _send_callback(
            client=merchant_client,
            payload=withdrawal_webhook,
        )

        # Verify withdrawal failed
        withdrawal_trx.refresh_from_db()
        assert withdrawal_trx.status == TransactionStatus.FAILED
        assert (
            withdrawal_trx.decline_code
            == muwe_spei_fixtures.MUWE_WITHDRAWAL_FAILED_WEBHOOK["errMsgCode"]
        )
        assert (
            withdrawal_trx.decline_reason
            == muwe_spei_fixtures.MUWE_WITHDRAWAL_FAILED_WEBHOOK["errMsg"]
        )
        assert (
            withdrawal_trx.extra[MUWE_SPEI_IDENTIFIER]
            == withdrawal_webhook[MUWE_SPEI_IDENTIFIER]
        )

    def test_get_transaction_status(self, wallet_muwe_spei):
        trx = PaymentTransactionFactory.create(
            type=TransactionType.WITHDRAWAL,
            wallet__wallet=wallet_muwe_spei,
            status=TransactionStatus.PENDING,
            id_in_payment_system=muwe_spei_fixtures.FOREIGN_ID_WITHDRAWAL,
        )

        client = MuweSpeiClient(trx.id)

        with requests_mock.Mocker() as m:
            # Test 1: SUCCESS status
            m.post(
                "https://test.sipelatam.mx/common/query/agentpay_order",
                json={
                    "resCode": "SUCCESS",
                    "mchId": 880924000000423,
                    "nonceStr": "testNonce123",
                    "sign": "FAKE_SIGNATURE",
                    "single": True,
                    "orderInfo": '{"orderId":"'
                    + muwe_spei_fixtures.FOREIGN_ID_WITHDRAWAL
                    + '","status":2,"amount":10000}',
                },
            )

            resp = client.get_transaction_status()
            assert isinstance(resp, RemoteTransactionStatus)
            assert resp.operation_status == TransactionStatus.SUCCESS
            assert resp.decline_code is None

            # Test 2: FAILED status with error details
            m.post(
                "https://test.sipelatam.mx/common/query/agentpay_order",
                json={
                    "resCode": "SUCCESS",
                    "mchId": 880924000000423,
                    "nonceStr": "testNonce456",
                    "sign": "FAKE_SIGNATURE",
                    "single": True,
                    "orderInfo": '{"orderId":"'
                    + muwe_spei_fixtures.FOREIGN_ID_WITHDRAWAL
                    + '","status":3,"errMsgCode":"40003","errMsg":"pay out not sufficient funds"}',
                },
            )

            resp = client.get_transaction_status()
            assert isinstance(resp, RemoteTransactionStatus)
            assert resp.operation_status == TransactionStatus.FAILED
            assert resp.decline_code == "40003"  # MUWE error code
            assert resp.decline_reason == "pay out not sufficient funds"

            # Test 3: PENDING status
            m.post(
                "https://test.sipelatam.mx/common/query/agentpay_order",
                json={
                    "resCode": "SUCCESS",
                    "mchId": 880924000000423,
                    "nonceStr": "testNonce789",
                    "sign": "FAKE_SIGNATURE",
                    "single": True,
                    "orderInfo": '{"orderId":"'
                    + muwe_spei_fixtures.FOREIGN_ID_WITHDRAWAL
                    + '","status":1}',
                },
            )

            resp = client.get_transaction_status()
            assert isinstance(resp, RemoteTransactionStatus)
            assert resp.operation_status == TransactionStatus.PENDING
            assert resp.decline_code is None

    def test_withdrawal_bank_not_found_slack_notification(
        self,
        merchant_client,
        wallet_muwe_spei,
        mock_send_callback,
        mock_check_status_task,
        mock_slack_send_message,
        disable_error_logs,
        disable_cache,
    ):
        customer_id = str(uuid.uuid4())
        with requests_mock.Mocker() as m:
            m.post(
                "https://test.sipelatam.mx/api/unified/collection/create",
                json=muwe_spei_fixtures.MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE,
            )

            resp = merchant_client.post(
                "/api/payment/v1/muwe-spei/create_instruction/",
                {
                    "wallet_id": wallet_muwe_spei.uuid,
                    "customer_id": customer_id,
                },
            )
            assert resp.status_code == 200

            _send_callback(
                client=merchant_client,
                payload=muwe_spei_fixtures.MUWE_DEPOSIT_SUCCESS_WEBHOOK,
            )

        resp = merchant_client.post(
            "/api/payment/v1/muwe-spei/withdraw/",
            {
                "wallet_id": wallet_muwe_spei.uuid,
                "amount": 100,
                "currency": "MXN",
                "withdraw_to_account": muwe_spei_fixtures.CLABE1,
                "user_data": {
                    "first_name": "Test",
                    "last_name": "User",
                },
                "customer_id": customer_id,
            },
            format="json",
        )

        assert resp.status_code == 201

        withdrawal_trx = PaymentTransaction.objects.filter(
            type=TransactionType.WITHDRAWAL
        ).first()
        assert withdrawal_trx
        assert withdrawal_trx.status == TransactionStatus.FAILED
        assert withdrawal_trx.decline_reason
        assert "bank list" in withdrawal_trx.decline_reason.lower()

        call_args = mock_slack_send_message.call_args
        assert call_args[1]["channel"] == SLACK_PS_STATUS_CHANNEL

        message = call_args[1]["text"]
        assert "failed withdrawal (bank is not available)" in message
        assert "User UUID" in message
        assert "Transaction ID" in message
        assert str(withdrawal_trx.uuid) in message


def _sign_webhook_payload(payload: dict[str, ty.Any]) -> dict[str, ty.Any]:
    payload_copy = payload.copy()
    api_key = muwe_spei_fixtures.MUWE_API_KEY
    payload_copy["sign"] = muwe_spei_helpers.calculate_signature(payload_copy, api_key)
    return payload_copy


def _send_callback(client: Client, payload: dict[str, ty.Any]) -> None:
    # Sign the payload before sending
    signed_payload = _sign_webhook_payload(payload)

    resp = client.post(
        "/api/payment/v1/callback/muwe-spei/",
        data=signed_payload,
        format="json",
    )
    assert resp.status_code == 200
