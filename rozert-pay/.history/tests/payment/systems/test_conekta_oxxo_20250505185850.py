import base64
import json
import re
from unittest.mock import Mock, call, patch
from uuid import uuid4

import pytest
import requests_mock
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (Encoding,
                                                          NoEncryption,
                                                          PrivateFormat,
                                                          PublicFormat)
from django.conf import settings
from django.core.exceptions import ValidationError
from pydantic import SecretStr
from rest_framework.test import APIClient
from rozert_pay.common import const
from rozert_pay.payment import entities
from rozert_pay.payment.admin import WalletForm
from rozert_pay.payment.models import (IncomingCallback, Merchant,
                                       PaymentTransaction, Wallet)
from rozert_pay.payment.systems.conekta.conekta_oxxo import (
    ConektaOxxoClient, ConektaOxxoCredentials,
    _validate_conekta_webhook_signature)
from tests.factories import PaymentSystemFactory, UserDataFactory


@pytest.mark.django_db
class TestConektaOxxoFlow:
    def test_deposit_flow_success(
        self,
        wallet_conekta_oxxo: Wallet,
        merchant_client: APIClient,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="https://conekta/orders/",
                json={
                    "object": "success",
                    "id": "123",
                    "charges": {
                        "data": [
                            {
                                "payment_method": {
                                    "reference": "123",
                                },
                            },
                        ],
                    },
                },
            )
            m.get(
                url=re.compile("https://conekta/orders/.*"),
                json={
                    "object": "success",
                    "id": "123",
                    "amount": 3001.00,
                    "currency": "MXN",
                    "payment_status": "paid",
                },
            )

            response = merchant_client.post(
                path="/api/payment/v1/conekta-oxxo/deposit/",
                data={
                    "wallet_id": wallet_conekta_oxxo.uuid,
                    "customer_id": None,
                    "amount": "3001",
                    "currency": "MXN",
                    "user_data": UserDataFactory.build().model_dump(),
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
                    data={
                        "type": "order.paid",
                        "data": {
                            "object": {
                                "metadata": {
                                    "transaction_uuid": str(trx.uuid),
                                },
                            },
                        },
                    },
                    format="json",
                )
            assert response.status_code == 200, response.content

            trx.refresh_from_db()
            assert trx.status == entities.TransactionStatus.SUCCESS

    def test_deposit_flow_pending_to_success(
        self,
        wallet_conekta_oxxo: Wallet,
        merchant_client: APIClient,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="https://conekta/orders/",
                json={
                    "object": "success",
                    "id": "123",
                    "charges": {
                        "data": [
                            {
                                "payment_method": {
                                    "reference": "123",
                                },
                            },
                        ],
                    },
                },
            )

            response = merchant_client.post(
                path="/api/payment/v1/conekta-oxxo/deposit/",
                data={
                    "wallet_id": wallet_conekta_oxxo.uuid,
                    "customer_id": None,
                    "amount": 3001.00,
                    "currency": "MXN",
                    "user_data": UserDataFactory.build().model_dump(),
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
                json={
                    "object": "order",
                    "id": "123",
                    "amount": 3001.00,
                    "currency": "MXN",
                    "payment_status": "pending_payment",
                },
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
                json={
                    "object": "success",
                    "id": "123",
                    "amount": 3001.00,
                    "currency": "MXN",
                    "payment_status": "paid",
                },
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
                            },
                        },
                    },
                    format="json",
                )
            assert response.status_code == 200, response.content

            trx.refresh_from_db()
            assert trx.status == entities.TransactionStatus.SUCCESS

    def test_deposit_flow_decline(
        self,
        wallet_conekta_oxxo: Wallet,
        merchant_client: APIClient,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="https://conekta/orders/",
                json={
                    "object": "error",
                    "type": "parameter_validation_error",
                    "message": "The parameter amount is invalid.",
                    "code": "parameter_validation_error",
                    "details": [
                        {
                            "param": "amount",
                            "message": "The parameter amount is invalid.",
                        },
                    ],
                },
            )

            response = merchant_client.post(
                path="/api/payment/v1/conekta-oxxo/deposit/",
                data={
                    "wallet_id": wallet_conekta_oxxo.uuid,
                    "customer_id": None,
                    "amount": "3001",
                    "currency": "MXN",
                    "user_data": UserDataFactory.build().model_dump(),
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

    def test_credentials_action(self, merchant: Merchant):
        system = PaymentSystemFactory.create(
            type=const.PaymentSystemType.CONEKTA_OXXO,
            name="conekta_oxxo",
        )
        form = WalletForm(
            data={
                "merchant": merchant,
                "system": system,
                "credentials": {
                    "private_key": "123",
                    "public_key": "5465",
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
                url=re.compile("/webhooks"),
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
                url=re.compile("/webhooks"),
                json={
                    "id": "14456",
                    "url": "https://test.ru",
                },
            )

            form.save()

            assert spy.call_args == call(
                "Credentials change action performed successfully", 25
            )

    def test_setup_webhooks(self):
        creds = ConektaOxxoCredentials(
            base_url="https://conekta.com",
            private_key=SecretStr("test_secret"),
            public_key=SecretStr("test_secret"),
        )
        webhook_url = f"{settings.EXTERNAL_ROZERT_HOST}/webhook"

        with requests_mock.Mocker() as m:
            m.get(
                "https://conekta.com/webhooks",
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
                status_code=400,
                json={
                    "deleted": False,
                    "id": "228",
                    "url": "https://old-webhook.ru",
                },
            )
            m.post(
                "https://conekta.com/webhooks",
                json={
                    "id": "1449",
                    "url": webhook_url,
                    "synchronous": "false",
                },
                status_code=201,
            )

            ConektaOxxoClient.setup_webhooks(
                url=webhook_url, creds=creds, logger=Mock()
            )

            assert m.call_count == 2

            create_request = m.request_history[0]
            assert create_request.method == "POST"
            assert create_request.url == "https://conekta.com/webhooks"
            assert create_request.json() == {
                "synchronous": "false",
                "url": webhook_url,
            }


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
            private_key=SecretStr("test_private_key"),
            public_key=SecretStr(rsa_key_pair["public_pem"]),
            base_url="https://api.conekta.io",
        )
        message = json.dumps(webhook_payload).encode("utf-8")
        signature = rsa_key_pair["private_key"].sign(
            message, padding.PKCS1v15(), hashes.SHA256()
        )

        callback = Mock(spec=IncomingCallback)
        callback.headers = {"DIGEST": base64.b64encode(signature).decode("utf-8")}

        _validate_conekta_webhook_signature(credentials, callback, webhook_payload)

        # Invalid signature
        fraud_payload = webhook_payload.copy()
        fraud_payload["data"]["object"]["id"] = "fraud_id"

        original_message = json.dumps(webhook_payload).encode("utf-8")
        signature = rsa_key_pair["private_key"].sign(
            original_message, padding.PKCS1v15(), hashes.SHA256()
        )

        fraud_callback = Mock(spec=IncomingCallback)
        fraud_callback.headers = {"DIGEST": base64.b64encode(signature).decode("utf-8")}

        with pytest.raises(ValidationError, match="Invalid Conekta webhook signature"):
            _validate_conekta_webhook_signature(credentials, callback, fraud_payload)

    def test_missing_digest_header(self, rsa_key_pair, webhook_payload):
        credentials = ConektaOxxoCredentials(
            private_key=SecretStr("test_private_key"),
            public_key=SecretStr(rsa_key_pair["public_pem"]),
            base_url="https://api.conekta.io",
        )
        callback = Mock(spec=IncomingCallback)
        callback.headers = {}

        with pytest.raises(ValidationError, match="Missing DIGEST header"):
            _validate_conekta_webhook_signature(credentials, callback, webhook_payload)

    def test_non_rsa_key(self, webhook_payload):
        # Create a mock callback
        callback = Mock(spec=IncomingCallback)
        callback.headers = {"DIGEST": "some-signature"}

        # Create credentials with invalid public key (not RSA)
        credentials = ConektaOxxoCredentials(
            private_key=SecretStr("test_private_key"),
            public_key=SecretStr(
                "-----BEGIN PUBLIC KEY-----\nInvalid Key\n-----END PUBLIC KEY-----"
            ),
            base_url="https://api.conekta.io",
        )

        # Should raise an assertion error when trying to load the key
        with pytest.raises(Exception):
            _validate_conekta_webhook_signature(credentials, callback, webhook_payload)
