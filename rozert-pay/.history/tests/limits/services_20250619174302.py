import base64
import json
import re
from decimal import Decimal
from unittest.mock import Mock, call, patch
from uuid import uuid4

import pytest
import requests_mock
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from django.conf import settings
from django.core.exceptions import ValidationError
from pydantic import SecretStr
from rest_framework.test import APIClient
from rozert_pay.common import const
from rozert_pay.payment import entities
from rozert_pay.payment.admin import WalletForm
from rozert_pay.payment.models import (
    IncomingCallback,
    Merchant,
    PaymentTransaction,
    Wallet,
)
from rozert_pay.payment.systems.conekta.conekta_oxxo import (
    ConektaOxxoClient,
    ConektaOxxoCredentials,
    _validate_conekta_webhook_signature,
)
from tests.factories import PaymentSystemFactory
from tests.payment.systems.conekta_oxxo.constants import (
    DECLINE_CREATE_DEPOSIT,
    IGNORING_CALLBACK_MOCK_BODY,
    PENDING_CREATE_DEPOSIT,
    SUCCESS_CREATE_DEPOSIT,
    SUCCESS_GET_DEPOSIT_STATUS,
    TRANSACTION_STATUS_NOT_FOUND,
    USER_DATA,
    WEBHOOK_KEYS_MOCK_BODY,
)


@pytest.mark.django_db
class TestCustomerLimits:
    def test_customer_limit_success(
        self,
        merchant_client: APIClient,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="https://conekta/orders/",
                json=SUCCESS_CREATE_DEPOSIT,
            )
            m.get(
                url=re.compile("https://conekta/orders/.*"),
                json=SUCCESS_GET_DEPOSIT_STATUS,
            )

            response = merchant_client.post(
                path="/api/payment/v1/conekta-oxxo/deposit/",
                data={
                    "wallet_id": wallet_conekta_oxxo.uuid,
                    "customer_id": None,
                    "amount": "30.01",
                    "currency": "MXN",
                    "user_data": USER_DATA,
                    "redirect_url": "http://example.com",
                    "callback_url": "http://google.com",
                },
                format="json",
            )

            assert response.status_code == 201, response.json()
            trx = PaymentTransaction.objects.get()
            assert trx.status == entities.TransactionStatus.PENDING
            assert trx.instruction == {
                "reference": "50 cent",
                "type": "instruction_reference",
            }

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json()["instruction"] == {
                "reference": "50 cent",
                "type": "instruction_reference",
            }

            trx.refresh_from_db()
            trx.status = entities.TransactionStatus.PENDING
            trx.save()

            with patch(
                "rozert_pay.payment.systems.conekta.conekta_oxxo._validate_conekta_webhook_signature",
                return_value=True,
            ):
                response = merchant_client.post(
                    path="/api/payment/v1/callback/conekta-oxxo/",
                    data={
                        "type": "order.paid",
                        "data": {
                            "object": {
                                "metadata": {
                                    "transaction_uuid": str(trx.uuid),
                                },
                                "order_id": "123",
                            },
                        },
                    },
                    format="json",
                )
            assert response.status_code == 200, response.content

            trx.refresh_from_db()
            assert trx.amount == Decimal("30.01")
            assert trx.status == entities.TransactionStatus.SUCCESS

    def test_deposit_flow_success_sandbox(
        self,
        wallet_conekta_oxxo_sandbox: Wallet,
        merchant_sandbox_client: APIClient,
    ):
        response = merchant_sandbox_client.post(
            path="/api/payment/v1/conekta-oxxo/deposit/",
            data={
                "wallet_id": wallet_conekta_oxxo_sandbox.uuid,
                "customer_id": None,
                "amount": "3001",
                "currency": "MXN",
                "user_data": USER_DATA,
                "redirect_url": "http://example.com",
                "callback_url": "http://google.com",
            },
            format="json",
        )

        assert response.status_code == 201, response.json()
        trx = PaymentTransaction.objects.get()
        assert trx.status == entities.TransactionStatus.SUCCESS

        response = merchant_sandbox_client.get(
            f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200

    def test_deposit_flow_pending_to_success(
        self,
        wallet_conekta_oxxo: Wallet,
        merchant_client: APIClient,
        mock_final_status_validation,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="https://conekta/orders/",
                json=SUCCESS_CREATE_DEPOSIT,
            )

            response = merchant_client.post(
                path="/api/payment/v1/conekta-oxxo/deposit/",
                data={
                    "wallet_id": wallet_conekta_oxxo.uuid,
                    "customer_id": None,
                    "amount": "30.01",
                    "currency": "MXN",
                    "user_data": USER_DATA,
                    "redirect_url": "http://example.com",
                    "callback_url": "http://google.com",
                },
                format="json",
            )

            assert response.status_code == 201, response.json()
            trx = PaymentTransaction.objects.get()
            assert trx.status == entities.TransactionStatus.PENDING

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200

            m.get(
                url=re.compile("https://conekta/orders/.*"),
                json=PENDING_CREATE_DEPOSIT,
            )

            with patch(
                "rozert_pay.payment.systems.conekta.conekta_oxxo._validate_conekta_webhook_signature",
                return_value=True,
            ):
                response = merchant_client.post(
                    path="/api/payment/v1/callback/conekta-oxxo/",
                    data={
                        "type": "order.paid",
                        "data": {
                            "object": {
                                "metadata": {
                                    "transaction_uuid": str(trx.uuid),
                                },
                                "order_id": "123",
                            },
                        },
                    },
                    format="json",
                )
            assert response.status_code == 200, response.content

            trx.refresh_from_db()
            assert trx.status == entities.TransactionStatus.PENDING

            m.get(
                url=re.compile("https://conekta/orders/.*"),
                json=SUCCESS_GET_DEPOSIT_STATUS,
            )

            with patch(
                "rozert_pay.payment.systems.conekta.conekta_oxxo._validate_conekta_webhook_signature",
                return_value=True,
            ):
                response = merchant_client.post(
                    path="/api/payment/v1/callback/conekta-oxxo/",
                    data={
                        "type": "order.paid",
                        "data": {
                            "object": {
                                "metadata": {
                                    "transaction_uuid": str(trx.uuid),
                                },
                                "order_id": "123",
                            },
                        },
                    },
                    format="json",
                )
            assert response.status_code == 200, response.content

            trx.refresh_from_db()
            assert trx.amount == Decimal("30.01")
            assert trx.status == entities.TransactionStatus.SUCCESS

    def test_deposit_flow_decline(
        self,
        wallet_conekta_oxxo: Wallet,
        merchant_client: APIClient,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="https://conekta/orders/",
                json=DECLINE_CREATE_DEPOSIT,
            )

            response = merchant_client.post(
                path="/api/payment/v1/conekta-oxxo/deposit/",
                data={
                    "wallet_id": wallet_conekta_oxxo.uuid,
                    "customer_id": None,
                    "amount": "3001",
                    "currency": "MXN",
                    "user_data": USER_DATA,
                    "redirect_url": "http://example.com",
                    "callback_url": "http://google.com",
                },
                format="json",
            )

            assert response.status_code == 201, response.json()
            trx = PaymentTransaction.objects.get()
            assert trx.status == entities.TransactionStatus.FAILED
            assert trx.decline_code == "parameter_validation_error"
            assert (
                trx.decline_reason
                == "[{'param': 'amount', 'message': 'The parameter amount is invalid.'}]"
            )

    def test_deposit_flow_decline_because_not_found(
        self,
        wallet_conekta_oxxo: Wallet,
        merchant_client: APIClient,
        mock_final_status_validation,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="https://conekta/orders/",
                json=PENDING_CREATE_DEPOSIT,
            )

            response = merchant_client.post(
                path="/api/payment/v1/conekta-oxxo/deposit/",
                data={
                    "wallet_id": wallet_conekta_oxxo.uuid,
                    "customer_id": None,
                    "amount": 3001.00,
                    "currency": "MXN",
                    "user_data": USER_DATA,
                    "redirect_url": "http://example.com",
                    "callback_url": "http://google.com",
                },
                format="json",
            )

            assert response.status_code == 201, response.json()
            trx = PaymentTransaction.objects.get()
            assert trx.status == entities.TransactionStatus.PENDING

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200

            m.get(
                url=re.compile("https://conekta/orders/.*"),
                json=TRANSACTION_STATUS_NOT_FOUND,
            )

            with patch(
                "rozert_pay.payment.systems.conekta.conekta_oxxo._validate_conekta_webhook_signature",
                return_value=True,
            ):
                response = merchant_client.post(
                    path="/api/payment/v1/callback/conekta-oxxo/",
                    data={
                        "type": "order.paid",
                        "data": {
                            "object": {
                                "metadata": {
                                    "transaction_uuid": str(trx.uuid),
                                },
                                "order_id": "123",
                            },
                        },
                    },
                    format="json",
                )
            assert response.status_code == 200, response.content

            trx.refresh_from_db()
            assert trx.status == entities.TransactionStatus.FAILED
            assert trx.decline_code == "resource_not_found_error"
            assert (
                trx.decline_reason
                == "[{'param': 'id', 'message': 'The resource you requested could not be found.'}]"
            )

    def test_credentials_action(self, merchant: Merchant):
        system = PaymentSystemFactory.create(
            type=const.PaymentSystemType.CONEKTA_OXXO,
            name="conekta_oxxo",
        )
        form = WalletForm(
            data={
                "merchant": merchant.id,
                "system": system.id,
                "credentials": {
                    "api_token": "123",
                    "webhook_public_key": "5465",
                    "base_url": "https://conekta.com",
                },
                "name": "test",
                "uuid": str(uuid4()),
                "sandbox_finalization_delay_seconds": 0,
            }
        )
        form.message_user = spy = Mock()

        assert form.is_valid(), form.errors

        with requests_mock.Mocker() as m:
            m.get(
                url=re.compile("/webhook_keys/"),
                json=WEBHOOK_KEYS_MOCK_BODY,
            )
            m.get(
                url=re.compile("/webhooks/"),
                json={
                    "has_more": False,
                    "data": [
                        {
                            "deleted": False,
                            "id": "14456",
                            "url": "https://test.ru",
                        }
                    ],
                },
            )
            m.delete(url=re.compile("/webhooks/14456"), json={})
            m.post(
                url=re.compile("/webhooks/"),
                json={
                    "id": "14456",
                    "url": "https://test.ru",
                },
            )

            form.save()

            assert spy.call_args == call(
                "Credentials change action performed successfully", 25
            )

            creds = Wallet.objects.get().credentials
            assert (
                creds["webhook_public_key"]
                == WEBHOOK_KEYS_MOCK_BODY["data"][0]["public_key"]
            )

    def test_setup_webhooks(self, wallet_conekta_oxxo: Wallet):
        creds = ConektaOxxoCredentials(
            base_url="https://conekta.com",
            api_token=SecretStr("test_secret"),
            webhook_public_key=SecretStr("test_secret"),
        )
        webhook_url = f"{settings.EXTERNAL_ROZERT_HOST}/webhook"

        with requests_mock.Mocker() as m:
            m.get(
                url=re.compile("/webhook_keys/"),
                json=WEBHOOK_KEYS_MOCK_BODY,
            ),
            m.get(
                "https://conekta.com/webhooks/",
                json={
                    "has_more": False,
                    "data": [
                        {
                            "deleted": False,
                            "id": "228",
                            "url": "https://old-webhook.ru",
                        }
                    ],
                },
            )
            m.delete(
                "https://conekta.com/webhooks/228",
                status_code=200,
                json={
                    "deleted": False,
                    "id": "228",
                    "url": "https://old-webhook.ru",
                },
            )
            m.post(
                "https://conekta.com/webhooks/",
                json={
                    "id": "1449",
                    "url": webhook_url,
                    "synchronous": "false",
                },
                status_code=201,
            )

            ConektaOxxoClient.setup_webhooks(
                url=webhook_url,
                creds=creds,
                logger=Mock(),
                wallet=wallet_conekta_oxxo,
                remove_existing=True,
            )

            assert m.call_count == 5

            create_request = m.request_history[0]
            assert create_request.method == "GET"
            create_request = m.request_history[1]
            assert create_request.method == "DELETE"
            create_request = m.request_history[2]
            assert create_request.method == "POST"
            assert create_request.url == "https://conekta.com/webhooks/"
            assert create_request.json() == {
                "synchronous": "false",
                "url": webhook_url,
            }

    def test_ignored_callback(
        self,
        wallet_conekta_oxxo: Wallet,
        merchant_client: APIClient,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="https://conekta/orders/",
                json=SUCCESS_CREATE_DEPOSIT,
            )
            m.get(
                url=re.compile("https://conekta/orders/.*"),
                json=SUCCESS_GET_DEPOSIT_STATUS,
            )

            response = merchant_client.post(
                path="/api/payment/v1/conekta-oxxo/deposit/",
                data={
                    "wallet_id": wallet_conekta_oxxo.uuid,
                    "customer_id": None,
                    "amount": "3001",
                    "currency": "MXN",
                    "user_data": USER_DATA,
                    "redirect_url": "http://example.com",
                    "callback_url": "http://google.com",
                },
                format="json",
            )

            assert response.status_code == 201, response.json()
            trx = PaymentTransaction.objects.get()
            assert trx.status == entities.TransactionStatus.PENDING

            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200

            with patch(
                "rozert_pay.payment.systems.conekta.conekta_oxxo._validate_conekta_webhook_signature",
                return_value=True,
            ):
                response = merchant_client.post(
                    path="/api/payment/v1/callback/conekta-oxxo/",
                    data=IGNORING_CALLBACK_MOCK_BODY,
                    format="json",
                )
            assert response.status_code == 200, response.content

            trx.refresh_from_db()
            assert trx.status == entities.TransactionStatus.PENDING


class TestConektaWebhookSignature:
    @pytest.fixture
    def rsa_key_pair(self):
        # Generate a new RSA key pair for testing
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        # Serialize keys to PEM format
        private_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        ).decode("utf-8")

        public_pem = public_key.public_bytes(
            encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")

        return {
            "private_key": private_key,
            "public_key": public_key,
            "private_pem": private_pem,
            "public_pem": public_pem,
        }

    @pytest.fixture
    def webhook_payload(self):
        return {
            "type": "order.paid",
            "data": {
                "object": {
                    "id": "ord_2tMKqPxrPpzKgqWaA",
                    "metadata": {
                        "transaction_uuid": "12345678-1234-5678-1234-567812345678"
                    },
                }
            },
        }

    def test_valid_signature(self, rsa_key_pair, webhook_payload):
        # Valid signature
        credentials = ConektaOxxoCredentials(
            api_token=SecretStr("test_private_key"),
            webhook_public_key=SecretStr(rsa_key_pair["public_pem"]),
            base_url="https://api.conekta.io",
        )
        message = json.dumps(webhook_payload).encode("utf-8")
        signature = rsa_key_pair["private_key"].sign(
            message, padding.PKCS1v15(), hashes.SHA256()
        )

        callback = Mock(spec=IncomingCallback)
        callback.headers = {"digest": base64.b64encode(signature).decode("utf-8")}

        _validate_conekta_webhook_signature(credentials, callback, webhook_payload)

    def test_invalid_signature(self, rsa_key_pair, webhook_payload):
        # Invalid signature
        credentials = ConektaOxxoCredentials(
            api_token=SecretStr("test_private_key"),
            webhook_public_key=SecretStr(rsa_key_pair["public_pem"]),
            base_url="https://api.conekta.io",
        )

        # Create a completely different message to sign
        different_payload = {
            "type": "different.event",
            "data": {
                "object": {
                    "id": "different_id",
                    "metadata": {"transaction_uuid": "different-uuid"},
                }
            },
        }

        # Sign the different message
        different_message = json.dumps(different_payload).encode("utf-8")
        signature = rsa_key_pair["private_key"].sign(
            different_message, padding.PKCS1v15(), hashes.SHA256()
        )

        # Create mock callback with signature from different message
        callback = Mock(spec=IncomingCallback)
        callback.headers = {"digest": base64.b64encode(signature).decode("utf-8")}

        # Verify with original webhook payload - should fail validation
        with pytest.raises(ValidationError, match="Invalid Conekta webhook signature"):
            _validate_conekta_webhook_signature(credentials, callback, webhook_payload)

    def test_missing_digest_header(self, rsa_key_pair, webhook_payload):
        credentials = ConektaOxxoCredentials(
            api_token=SecretStr("test_private_key"),
            webhook_public_key=SecretStr(rsa_key_pair["public_pem"]),
            base_url="https://api.conekta.io",
        )
        callback = Mock(spec=IncomingCallback)
        callback.headers = {}

        with pytest.raises(ValidationError, match="Missing DIGEST header"):
            _validate_conekta_webhook_signature(credentials, callback, webhook_payload)

    def test_non_rsa_key(self, webhook_payload):
        # Create a mock callback
        callback = Mock(spec=IncomingCallback)
        callback.headers = {"digest": "some-signature"}

        # Create credentials with invalid public key (not RSA)
        credentials = ConektaOxxoCredentials(
            api_token=SecretStr("test_private_key"),
            webhook_public_key=SecretStr(
                "-----BEGIN PUBLIC KEY-----\nInvalid Key\n-----END PUBLIC KEY-----"
            ),
            base_url="https://api.conekta.io",
        )

        # Should raise an assertion error when trying to load the key
        with pytest.raises(Exception):
            _validate_conekta_webhook_signature(credentials, callback, webhook_payload)
