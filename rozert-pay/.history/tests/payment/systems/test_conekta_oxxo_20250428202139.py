import logging
import re
from decimal import Decimal
from unittest import mock
from unittest.mock import Mock, call, patch
from uuid import uuid4

import pytest
import requests_mock
from django.conf import settings
from pydantic import SecretStr
from rest_framework.test import APIClient
from rozert_pay.common import const
from rozert_pay.common.const import PaymentSystemType, TransactionStatus
from rozert_pay.payment import entities, tasks
from rozert_pay.payment.admin import WalletForm
from rozert_pay.payment.factories import get_payment_system_controller_by_type
from rozert_pay.payment.models import (CurrencyWallet, PaymentTransaction,
                                       Wallet)
from rozert_pay.payment.services import errors
from rozert_pay.payment.systems.conekta.conekta_oxxo import (
    ConektaOxxoClient, ConektaOxxoCredentials)
from tests.factories import (PaymentSystemFactory, PaymentTransactionFactory,
                             UserDataFactory)
from tests.payment.api_v1 import matchers


@pytest.mark.django_db
class TestConektaOxxoFlow:

    def test_deposit_flow_success(
        self,
        wallet_conekta_oxxo: Wallet,
        merchant_client: APIClient,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url='https://conekta/orders/',
                json={
                    'object': 'success',
                    'id': '123',
                    'charges': {
                        'data': [
                            {
                                'payment_method': {
                                    'reference': '123',
                                },
                            },
                        ],
                    },
                },
            )
            m.get(
                url=re.compile('https://conekta/orders/.*'),
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

    def test_deposit_flow_decline(
        self,
        wallet_conekta_oxxo: Wallet,
        merchant_client: APIClient,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url='https://conekta/orders/',
                json={
                    'object': 'success',
                    'id': '123',
                    'charges': {
                        'data': [
                            {
                                'payment_method': {
                                    'reference': '123',
                                },
                            },
                        ],
                    },
                },
            )
            m.get(
                url=re.compile('https://conekta/orders/.*'),
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

    def test_callback(self, merchant_client, wallet_conekta_oxxo):
        currency_wallet = CurrencyWallet.objects.create(
            wallet=wallet_conekta_oxxo,
            currency="USD",
        )

        trx = PaymentTransaction.objects.create(
            currency="USD",
            wallet=currency_wallet,
            amount=Decimal("100.00"),
            id_in_payment_system="ORDER_ID_123",
            type=const.TransactionType.DEPOSIT,
            status=entities.TransactionStatus.PENDING,
        )

        with requests_mock.Mocker() as m:
            m.post(
                url=re.compile("/v1/oauth2/token"),
                json={
                    "expires_in": 100,
                    "access_token": "token",
                },
            )

            m.get(
                url=re.compile("/v2/checkout/orders/ORDER_ID_123"),
                json={
                    "id": "ORDER_ID_123",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "captureID",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                    "payer": {
                        "email_address": "test@test.ru",
                    },
                },
            )
            m.post(
                url=re.compile("/v2/checkout/orders/ORDER_ID_123/capture"),
                json={
                    "id": "ORDER_ID_123",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "captureID",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                    "payer": {
                        "email_address": "test@test.ru",
                    },
                },
            )
            m.get(
                url=re.compile("/v1/notifications/webhooks"),
                json={
                    "webhooks": [
                        {
                            "id": "123",
                            "url": "https://test.ru",
                        }
                    ]
                },
            )
            m.post(
                url=re.compile("/v1/notifications/verify-webhook-signature"),
                json={
                    "verification_status": "SUCCESS",
                },
            )
            m.get(
                url=re.compile("/v2/payments/captures/captureID"),
                json={
                    "id": "ORDER_ID_123",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "captureID",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                    "payer": {
                        "email_address": "test@test.ru",
                    },
                },
            )

            response = merchant_client.post(
                "/api/payment/v1/callback/paypal/",
                {
                    "id": "WEBHOOK_EVENT_ID",
                    "resource": {
                        "id": "ORDER_ID_123",
                        "status": "APPROVED",
                    },
                },
                format="json",
            )
            assert response.status_code == 200, response.content

        trx.refresh_from_db()
        assert trx.status == entities.TransactionStatus.SUCCESS

    def test_credentials_action(self, merchant):
        system = PaymentSystemFactory.create(
            type=const.PaymentSystemType.PAYPAL,
            name="paypal",
        )
        form = WalletForm(
            data={
                "merchant": merchant,
                "system": system,
                "credentials": {
                    "key": 1,
                    "value": 2,
                },
                "name": "test",
                "uuid": str(uuid4()),
                "sandbox_finalization_delay_seconds": 0,
            }
        )
        form.message_user = spy = Mock()

        assert form.is_valid(), form.errors

        with requests_mock.Mocker() as m:
            m.post(
                url=re.compile("/v1/oauth2/token"),
                json={
                    "expires_in": 100,
                    "access_token": "token",
                },
            )
            m.get(
                url=re.compile("/v1/notifications/webhooks"),
                json={
                    "webhooks": [
                        {
                            "id": "123",
                            "url": "https://test.ru",
                        }
                    ]
                },
            )
            m.delete(url=re.compile("/v1/notifications/webhooks/123"), json={})
            m.post(
                url=re.compile("/v1/notifications/webhooks"),
                json={
                    "id": "123",
                    "url": "https://test.ru",
                },
            )

            form.save()

            assert spy.call_args == call(
                "Credentials change action performed successfully", 25
            )

    def test_setup_webhooks(self):
        creds = PaypalCredentials(
            base_url="https://api-m.sandbox.paypal.com",
            client_id="test_client_id",
            client_secret=SecretStr("test_secret"),
            test_mode=True,
        )
        webhook_url = f"{settings.EXTERNAL_ROZERT_HOST}/webhook"

        with requests_mock.Mocker() as m:
            m.post(
                "https://api-m.sandbox.paypal.com/v1/oauth2/token",
                json={"access_token": "test_token", "expires_in": 3600},
            )
            m.get(
                "https://api-m.sandbox.paypal.com/v1/notifications/webhooks",
                json={"webhooks": [{"id": "WH-001", "url": "https://old-webhook.com"}]},
            )
            m.delete(
                "https://api-m.sandbox.paypal.com/v1/notifications/webhooks/WH-001",
                status_code=400,
                json={"error": "Bad Request"},
            )
            m.post(
                "https://api-m.sandbox.paypal.com/v1/notifications/webhooks",
                json={"id": "WH-003", "url": webhook_url},
                status_code=201,
            )

            PaypalClient.setup_webhooks(url=webhook_url, creds=creds, logger=Mock())

            assert m.call_count == 4

            create_request = m.request_history[-3]
            assert create_request.method == "POST"
            assert (
                create_request.url
                == "https://api-m.sandbox.paypal.com/v1/notifications/webhooks"
            )
            assert create_request.json() == {
                "event_types": [{"name": "*"}],
                "url": webhook_url,
            }

    def test_deposit_finalize_unprocessable_entity(self, currency_wallet_paypal):
        controller = get_payment_system_controller_by_type(PaymentSystemType.PAYPAL)

        trx: PaymentTransaction = PaymentTransactionFactory.create(
            wallet=currency_wallet_paypal,
            extra={
                PaypalTransactionExtraFields.PAYPAL_ORDER_ID: "ORDER_ID_123",
            },
        )

        with requests_mock.Mocker() as m:
            m.post(
                url=re.compile("/v1/oauth2/token"),
                json={
                    "expires_in": 100,
                    "access_token": "token",
                },
            )
            m.post(
                url=re.compile("/v2/checkout/orders/.*/capture"),
                status_code=422,
                json={
                    "name": "UNPROCESSABLE_ENTITY",
                    "links": [
                        {
                            "rel": "information_link",
                            "href": "https://developer.paypal.com/api/rest/reference/orders/v2/errors/#INSTRUMENT_DECLINED",
                            "method": "GET",
                        },
                        {
                            "rel": "redirect",
                            "href": "https://www.sandbox.paypal.com/checkoutnow?token=1LW07307UP276402J",
                            "method": "GET",
                        },
                    ],
                    "details": [
                        {
                            "issue": "INSTRUMENT_DECLINED",
                            "description": "The instrument presented  was either declined by the processor or bank, or it can't be used for this payment.",
                        }
                    ],
                    "message": "The requested action could not be performed, semantically incorrect, or failed business validation.",
                    "debug_id": "f7707100bc347",
                },
            )

            controller.run_deposit_finalization(trx.id)
            trx.refresh_from_db()

        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "UNPROCESSABLE_ENTITY"
        assert (
            trx.decline_reason
            == "The requested action could not be performed, semantically incorrect, or failed business validation."
        )
