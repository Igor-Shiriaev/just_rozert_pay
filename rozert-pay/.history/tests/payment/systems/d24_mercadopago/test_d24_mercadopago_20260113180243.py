from copy import deepcopy
from decimal import Decimal
from unittest import mock

import requests_mock
from django.test import override_settings
from rest_framework.test import APIClient
from rozert_pay.common import const
from rozert_pay.common.const import CallbackStatus, TransactionStatus
from rozert_pay.payment.models import (
    CurrencyWallet,
    IncomingCallback,
    Merchant,
    PaymentTransaction,
    Wallet,
)
from rozert_pay_shared.tests_utils.d24_mercadopago import (
    DEPOSIT_REQUEST_PAYLOAD,
    WITHDRAW_REQUEST_PAYLOAD,
)
from tests.payment.api_v1 import matchers
from tests.payment.systems.d24_mercadopago.constants import (
    D24_MERCADO_PAGO_DEPOSIT_CALLBACK,
    D24_MERCADO_PAGO_DEPOSIT_FAILED_RESPONSE,
    D24_MERCADO_PAGO_DEPOSIT_GET_STATUS_FAILED_RESPONSE,
    D24_MERCADO_PAGO_DEPOSIT_GET_STATUS_SUCCESS_RESPONSE,
    D24_MERCADO_PAGO_DEPOSIT_SUCCESS_RESPONSE,
    D24_MERCADO_PAGO_WITHDRAWAL_CALLBACK,
    D24_MERCADO_PAGO_WITHDRAWAL_FAILED_RESPONSE,
    D24_MERCADO_PAGO_WITHDRAWAL_GET_STATUS_NOT_FOUND_RESPONSE,
    D24_MERCADO_PAGO_WITHDRAWAL_GET_STATUS_SUCCESS_RESPONSE,
    D24_MERCADO_PAGO_WITHDRAWAL_SUCCESS_RESPONSE,
    DEPOSIT_FOREIGN_ID,
    INVALID_CLABE,
    INVALID_MEXICAN_CURP,
    MEXICAN_VALID_CURP,
    VALID_CLABE,
    WITHDRAWAL_FOREIGN_ID,
)


class TestD24MercadoPagoSystem:
    def test_deposit_validation(
        self, merchant_client: APIClient, wallet_d24_mercadopago: Wallet
    ):
        # missing data
        response = merchant_client.post(
            path="/api/payment/v1/d24-mercadopago/deposit/",
            data={
                "amount": "2333.71",
                "currency": "MXN",
                "wallet_id": wallet_d24_mercadopago.uuid,
                "customer_id": "customer1",
                "user_data": {},
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.json() == {
            "redirect_url": ["This field is required."],
            "user_data": {
                "country": ["This field is required."],
                "phone": ["This field is required."],
                "email": ["This field is required."],
                "first_name": ["This field is required."],
                "last_name": ["This field is required."],
            },
            "mexican_curp": ["This field is required."],
        }

        # Invalid CURP
        response = merchant_client.post(
            path="/api/payment/v1/d24-mercadopago/deposit/",
            data={
                "amount": "2333.71",
                "currency": "MXN",
                "wallet_id": wallet_d24_mercadopago.uuid,
                "customer_id": "customer1",
                "user_data": {
                    "country": "MX",
                    "email": "test@test.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "phone": "1234567890",
                },
                "mexican_curp": "ssss101210mlllllj0",
                "redirect_url": "https://redirect.url",
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.json() == {
            "mexican_curp": ["User must be at least 18 years old"]
        }

    def test_withdraw_validation(
        self,
        merchant_client: APIClient,
        wallet_d24_mercadopago: Wallet,
    ):
        # missing data
        response = merchant_client.post(
            path="/api/payment/v1/d24-mercadopago/withdraw/",
            data={
                "amount": "2333.71",
                "currency": "MXN",
                "wallet_id": wallet_d24_mercadopago.uuid,
                "customer_id": "customer1",
                "user_data": {},
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.json() == {
            "user_data": {
                "country": ["This field is required."],
                "first_name": ["This field is required."],
                "last_name": ["This field is required."],
            },
            "mexican_curp": ["This field is required."],
            "withdraw_to_account": ["This field is required."],
        }

        # Invalid CURP and CLABE
        response = merchant_client.post(
            path="/api/payment/v1/d24-mercadopago/withdraw/",
            data={
                "amount": "2333.71",
                "currency": "MXN",
                "wallet_id": wallet_d24_mercadopago.uuid,
                "customer_id": "customer1",
                "user_data": {
                    "country": "MX",
                    "email": "test@test.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "phone": "1234567890",
                },
                "mexican_curp": INVALID_MEXICAN_CURP,
                "withdraw_to_account": INVALID_CLABE,
                "redirect_url": "https://redirect.url",
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.json() == {
            "withdraw_to_account": ["Invalid CLABE"],
            "mexican_curp": ["User must be at least 18 years old"],
        }

    def test_deposit_success(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_d24_mercadopago: Wallet,
        mock_send_callback,
        mock_check_status_task,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://api-stg.directa24.com/v3/deposits",
                json=D24_MERCADO_PAGO_DEPOSIT_SUCCESS_RESPONSE,
            )

            request_payload = deepcopy(DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_d24_mercadopago.uuid)
            request_payload["mexican_curp"] = MEXICAN_VALID_CURP

            response = merchant_client.post(
                path="/api/payment/v1/d24-mercadopago/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == DEPOSIT_FOREIGN_ID
            assert trx.check_status_until
            assert trx.status == TransactionStatus.PENDING

            m.get(
                f"https://api-stg.directa24.com/v3/deposits/{DEPOSIT_FOREIGN_ID}",
                json=D24_MERCADO_PAGO_DEPOSIT_GET_STATUS_SUCCESS_RESPONSE,
            )

            # Callback
            response = merchant_client.post(
                path="/api/payment/v1/callback/d24-mercadopago/",
                data=D24_MERCADO_PAGO_DEPOSIT_CALLBACK,
                format="json",
            )
            assert response.status_code == 200

            incoming_callback = IncomingCallback.objects.get()
            assert (
                incoming_callback.status == CallbackStatus.SUCCESS
            ), incoming_callback.error

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

            # Transaction status
            response = merchant_client.get(
                path=f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "success",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "phone": "+1234567890",
                        }
                    ),
                }
            )

    def test_deposit_failed_instantly(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_d24_mercadopago: Wallet,
        mock_check_status_task,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://api-stg.directa24.com/v3/deposits",
                json=D24_MERCADO_PAGO_DEPOSIT_FAILED_RESPONSE,
            )

            response = merchant_client.post(
                path="/api/payment/v1/d24-mercadopago/deposit/",
                data={
                    "amount": "2333.71",
                    "currency": "MXN",
                    "wallet_id": wallet_d24_mercadopago.uuid,
                    "customer_id": "customer1",
                    "user_data": {
                        "country": "MX",
                        "email": "test@test.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "phone": "1234567890",
                    },
                    "mexican_curp": MEXICAN_VALID_CURP,
                    "redirect_url": "https://redirect.url",
                },
                format="json",
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            assert trx.status == TransactionStatus.FAILED

    def test_deposit_failed_with_callback(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_d24_mercadopago: Wallet,
        mock_check_status_task,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://api-stg.directa24.com/v3/deposits",
                json=D24_MERCADO_PAGO_DEPOSIT_SUCCESS_RESPONSE,
            )

            response = merchant_client.post(
                path="/api/payment/v1/d24-mercadopago/deposit/",
                data={
                    "amount": "2333.71",
                    "currency": "MXN",
                    "wallet_id": wallet_d24_mercadopago.uuid,
                    "customer_id": "customer1",
                    "user_data": {
                        "country": "MX",
                        "email": "test@test.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "phone": "1234567890",
                    },
                    "mexican_curp": MEXICAN_VALID_CURP,
                    "redirect_url": "https://redirect.url",
                },
                format="json",
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == DEPOSIT_FOREIGN_ID
            assert trx.check_status_until
            assert trx.status == TransactionStatus.PENDING

            m.get(
                f"https://api-stg.directa24.com/v3/deposits/{DEPOSIT_FOREIGN_ID}",
                json=D24_MERCADO_PAGO_DEPOSIT_GET_STATUS_FAILED_RESPONSE,
            )

            # Callback
            response = merchant_client.post(
                path="/api/payment/v1/callback/d24-mercadopago/",
                data=D24_MERCADO_PAGO_DEPOSIT_CALLBACK,
                format="json",
            )
            trx.refresh_from_db()
            assert response.status_code == 200
            assert trx.status == TransactionStatus.FAILED
            assert trx.decline_code == "EXPIRED"
            assert (
                trx.decline_reason
                == "The deposit has reached its expiration time and the user did not pay"
            )

    def test_deposit_failed_with_callback_then_to_success_with_callback(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_d24_mercadopago: Wallet,
        mock_check_status_task,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://api-stg.directa24.com/v3/deposits",
                json=D24_MERCADO_PAGO_DEPOSIT_SUCCESS_RESPONSE,
            )

            response = merchant_client.post(
                path="/api/payment/v1/d24-mercadopago/deposit/",
                data={
                    "amount": "2333.71",
                    "currency": "MXN",
                    "wallet_id": wallet_d24_mercadopago.uuid,
                    "customer_id": "customer1",
                    "user_data": {
                        "country": "MX",
                        "email": "test@test.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "phone": "1234567890",
                    },
                    "mexican_curp": MEXICAN_VALID_CURP,
                    "redirect_url": "https://redirect.url",
                },
                format="json",
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == DEPOSIT_FOREIGN_ID
            assert trx.check_status_until
            assert trx.status == TransactionStatus.PENDING

            m.get(
                f"https://api-stg.directa24.com/v3/deposits/{DEPOSIT_FOREIGN_ID}",
                json=D24_MERCADO_PAGO_DEPOSIT_GET_STATUS_FAILED_RESPONSE,
            )

            # Callback
            response = merchant_client.post(
                path="/api/payment/v1/callback/d24-mercadopago/",
                data=D24_MERCADO_PAGO_DEPOSIT_CALLBACK,
                format="json",
            )
            trx.refresh_from_db()
            assert response.status_code == 200
            assert trx.status == TransactionStatus.FAILED
            assert trx.decline_code == "EXPIRED"
            assert (
                trx.decline_reason
                == "The deposit has reached its expiration time and the user did not pay"
            )

            # Then we send a success callback
            m.get(
                f"https://api-stg.directa24.com/v3/deposits/{DEPOSIT_FOREIGN_ID}",
                json=D24_MERCADO_PAGO_DEPOSIT_GET_STATUS_SUCCESS_RESPONSE,
            )
            response = merchant_client.post(
                path="/api/payment/v1/callback/d24-mercadopago/",
                data=D24_MERCADO_PAGO_DEPOSIT_CALLBACK,
                format="json",
            )
            trx.refresh_from_db()
            assert response.status_code == 200
            assert trx.status == TransactionStatus.SUCCESS
            assert trx.decline_code is None
            assert trx.decline_reason is None
    @
    def test_withdraw_success(
        self,
        merchant_client: APIClient,
        wallet_d24_mercadopago: Wallet,
        currency_wallet_d24_mercadopago: CurrencyWallet,
        mock_check_status_task,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://api-stg.directa24.com/v3/cashout",
                json=D24_MERCADO_PAGO_WITHDRAWAL_SUCCESS_RESPONSE,
            )

            request_payload = deepcopy(WITHDRAW_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_d24_mercadopago.uuid)
            request_payload["mexican_curp"] = MEXICAN_VALID_CURP
            request_payload["withdraw_to_account"] = VALID_CLABE

            response = merchant_client.post(
                path="/api/payment/v1/d24-mercadopago/withdraw/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == WITHDRAWAL_FOREIGN_ID
            assert trx.check_status_until
            assert trx.status == TransactionStatus.PENDING

            m.post(
                "https://api-stg.directa24.com/v3/cashout/status",
                json=D24_MERCADO_PAGO_WITHDRAWAL_GET_STATUS_SUCCESS_RESPONSE,
            )

            # Callback
            response = merchant_client.post(
                path="/api/payment/v1/callback/d24-mercadopago/",
                data=D24_MERCADO_PAGO_WITHDRAWAL_CALLBACK.format(
                    trx_uuid_placeholder=trx.uuid.hex
                ),
                format="json",
            )
            assert response.status_code == 200

            cb = IncomingCallback.objects.get()
            assert cb.status == CallbackStatus.SUCCESS, cb.error

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

            # Transaction status
            response = merchant_client.get(
                path=f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json() == matchers.DictContains(
                {
                    "amount": "2333.71",
                    "currency": "MXN",
                    "status": "success",
                    "type": "withdrawal",
                    "user_data": matchers.DictContains(
                        {
                            "first_name": "John",
                            "last_name": "Doe",
                        }
                    ),
                }
            )

    def test_withdraw_failed(
        self,
        merchant_client: APIClient,
        wallet_d24_mercadopago: Wallet,
        currency_wallet_d24_mercadopago: CurrencyWallet,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://api-stg.directa24.com/v3/cashout",
                json=D24_MERCADO_PAGO_WITHDRAWAL_FAILED_RESPONSE,
            )

            response = merchant_client.post(
                path="/api/payment/v1/d24-mercadopago/withdraw/",
                data={
                    "amount": "2333.71",
                    "currency": "MXN",
                    "wallet_id": wallet_d24_mercadopago.uuid,
                    "customer_id": "customer1",
                    "user_data": {
                        "country": "MX",
                        "first_name": "John",
                        "last_name": "Doe",
                    },
                    "mexican_curp": MEXICAN_VALID_CURP,
                    "withdraw_to_account": VALID_CLABE,
                },
                format="json",
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            assert trx.status == TransactionStatus.FAILED
            assert (
                trx.decline_reason
                == f"{D24_MERCADO_PAGO_WITHDRAWAL_FAILED_RESPONSE['message']}. {D24_MERCADO_PAGO_WITHDRAWAL_FAILED_RESPONSE['reason']}"
            )

    def test_withdraw_not_found(
        self,
        merchant_client: APIClient,
        wallet_d24_mercadopago: Wallet,
        currency_wallet_d24_mercadopago: CurrencyWallet,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://api-stg.directa24.com/v3/cashout",
                json=D24_MERCADO_PAGO_WITHDRAWAL_SUCCESS_RESPONSE,
            )
            m.post(
                "https://api-stg.directa24.com/v3/cashout/status",
                json=D24_MERCADO_PAGO_WITHDRAWAL_GET_STATUS_NOT_FOUND_RESPONSE,
            )

            response = merchant_client.post(
                path="/api/payment/v1/d24-mercadopago/withdraw/",
                data={
                    "amount": "2333.71",
                    "currency": "MXN",
                    "wallet_id": wallet_d24_mercadopago.uuid,
                    "customer_id": "customer1",
                    "user_data": {
                        "country": "MX",
                        "first_name": "John",
                        "last_name": "Doe",
                    },
                    "mexican_curp": MEXICAN_VALID_CURP,
                    "withdraw_to_account": VALID_CLABE,
                },
                format="json",
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            assert trx.amount == Decimal("2333.71")
            assert trx.status == TransactionStatus.FAILED
            assert (
                trx.decline_code == const.TransactionDeclineCodes.TRANSACTION_NOT_FOUND
            )
            assert trx.decline_reason == "Cashout not found with this ID"

            response = merchant_client.get(
                path=f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.json()["id"] == str(trx.uuid)
            assert response.json()["status"] == TransactionStatus.FAILED


class TestD24MercadoPagoSandboxSystem:
    def test_deposit_success_sandbox(
        self,
        merchant_sandbox_client,
        mock_send_callback,
        api_client,
        merchant_sandbox,
        wallet_d24_mercadopago_sandbox: Wallet,
        mock_on_commit,
        mock_check_status_task,
    ):
        response = merchant_sandbox_client.post(
            "/api/payment/v1/d24-mercadopago/deposit/",
            {
                "amount": "2333.71",
                "currency": "MXN",
                "wallet_id": wallet_d24_mercadopago_sandbox.uuid,
                "customer_id": "customer1",
                "user_data": {
                    "country": "MX",
                    "email": "test@test.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "phone": "1234567890",
                },
                "mexican_curp": MEXICAN_VALID_CURP,
                "redirect_url": "https://redirect.url",
            },
            format="json",
        )
        assert response.status_code == 201
        trx = PaymentTransaction.objects.get()

        assert trx.id_in_payment_system
        assert trx.check_status_until
        assert trx.status == TransactionStatus.SUCCESS

        # Transaction status
        response = api_client.get(
            f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200
        assert response.json() == matchers.DictContains(
            {
                "amount": "2333.71",
                "currency": "MXN",
                "status": "success",
                "type": "deposit",
                "user_data": matchers.DictContains(
                    {
                        "phone": "1234567890",
                    }
                ),
            }
        )

    def test_withdraw_success_sandbox(
        self,
        merchant_sandbox_client,
        mock_send_callback,
        api_client,
        merchant_sandbox,
        wallet_d24_mercadopago_sandbox: Wallet,
        currency_wallet_d24_mercadopago_sandbox: CurrencyWallet,
        mock_on_commit,
    ):
        response = merchant_sandbox_client.post(
            "/api/payment/v1/d24-mercadopago/withdraw/",
            {
                "amount": "2333.71",
                "currency": "MXN",
                "wallet_id": wallet_d24_mercadopago_sandbox.uuid,
                "user_data": {
                    "country": "MX",
                    "first_name": "John",
                    "last_name": "Doe",
                },
                "mexican_curp": MEXICAN_VALID_CURP,
                "withdraw_to_account": VALID_CLABE,
                "customer_id": "customer1",
            },
            format="json",
        )
        assert response.status_code == 201
        trx = PaymentTransaction.objects.get()

        assert trx.id_in_payment_system
        assert trx.check_status_until
        assert trx.status == TransactionStatus.SUCCESS

        # Transaction status
        response = api_client.get(
            f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200
        assert trx.customer
        assert response.json() == {
            "id": mock.ANY,
            "status": "success",
            "decline_code": None,
            "decline_reason": None,
            "card_token": None,
            "created_at": mock.ANY,
            "updated_at": mock.ANY,
            "instruction": None,
            "callback_url": None,
            "customer_id": mock.ANY,
            "type": "withdrawal",
            "currency": "MXN",
            "amount": "2333.71",
            "form": None,
            "external_account_id": "021790064060296642",
            "external_customer_id": str(trx.customer.external_id),
            "user_data": {
                "email": None,
                "phone": None,
                "first_name": "John",
                "language": None,
                "last_name": "Doe",
                "post_code": None,
                "city": None,
                "country": "MX",
                "province": None,
                "state": None,
                "address": None,
                "ip_address": None,
                "date_of_birth": None,
            },
            "wallet_id": str(wallet_d24_mercadopago_sandbox.uuid),
        }

    @mock.patch("rozert_pay.common.slack.slack_client.send_message")
    def test_expired_transaction_callback_notification(
        self,
        mock_slack_send_message,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_d24_mercadopago: Wallet,
        mock_send_callback,
        currency_wallet_d24_mercadopago: CurrencyWallet,
        mock_check_status_task,
    ):
        wallet_d24_mercadopago.system.ip_whitelist_enabled = False
        wallet_d24_mercadopago.system.save()

        with (
            requests_mock.Mocker() as m,
            override_settings(IS_PRODUCTION=True),
        ):
            m.post(
                "https://api-stg.directa24.com/v3/deposits",
                json=D24_MERCADO_PAGO_DEPOSIT_SUCCESS_RESPONSE,
            )

            request_payload = deepcopy(DEPOSIT_REQUEST_PAYLOAD)
            request_payload["wallet_id"] = str(wallet_d24_mercadopago.uuid)
            request_payload["mexican_curp"] = MEXICAN_VALID_CURP

            response = merchant_client.post(
                path="/api/payment/v1/d24-mercadopago/deposit/",
                data=request_payload,
                format="json",
            )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()

            trx.status = TransactionStatus.FAILED
            trx.decline_code = "EXPIRED"
            trx.save()

            m.get(
                f"https://api-stg.directa24.com/v3/deposits/{DEPOSIT_FOREIGN_ID}",
                json={
                    "user_id": "62dd744c-cbfa-4357-8ef0-460390e78b5c",
                    "deposit_id": DEPOSIT_FOREIGN_ID,
                    "status": "EXPIRED",
                    "currency": "MXN",
                    "local_amount": 100.00,
                },
            )

            callback_data = deepcopy(D24_MERCADO_PAGO_DEPOSIT_CALLBACK)
            response = merchant_client.post(
                path="/api/payment/v1/callback/d24-mercadopago/",
                data=callback_data,
                format="json",
            )

            assert response.status_code == 200

            call_args = mock_slack_send_message.call_args

            assert str(trx.uuid) in call_args.kwargs["text"]
            assert "expired" in call_args.kwargs["text"].lower()
            assert "rozert_d24_mercadopago" in call_args.kwargs["text"]
