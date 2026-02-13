import logging
import re
from decimal import Decimal
from unittest import mock
from unittest.mock import Mock, call
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
from rozert_pay.payment.models import CurrencyWallet, PaymentTransaction
from rozert_pay.payment.services import errors
from rozert_pay.payment.systems.conekta.conekta_oxxo import (
    ConektaOxxoClient, ConektaOxxoCredentials)
from tests.factories import (PaymentSystemFactory, PaymentTransactionFactory,
                             UserDataFactory)
from tests.payment.api_v1 import matchers


@pytest.mark.django_db
class TestConektaOxxoFlow:
    def test_deposit_flow(self, wallet_conekta_oxxo, merchant_client: APIClient):
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
                    "amount": 41540,
                    "currency": "MXN",
                    "payment_status": "paid",
                },
            )
            m.post(
                url=re.compile("/v1/oauth2/token"),
                json={
                    "expires_in": 100,
                    "access_token": "token",
                },
            )

            m.post(
                url=re.compile("/v2/checkout/orders$"),
                json={
                    "id": "ORDER_ID_123",
                    "links": [
                        {
                            "href": "https://api.sandbox.paypal.com/v2/checkout"
                            "/orders/ORDER_ID_123",
                            "method": "GET",
                            "rel": "self",
                        },
                        {
                            "href": "https://www.sandbox.paypal.com/checkoutnow"
                            "?token=ORDER_ID_123",
                            "method": "GET",
                            "rel": "approve",
                        },
                        {
                            "href": "https://api.sandbox.paypal.com/v2/checkout"
                            "/orders/ORDER_ID_123",
                            "method": "PATCH",
                            "rel": "update",
                        },
                        {
                            "href": "https://api.sandbox.paypal.com/v2/checkout"
                            "/orders/ORDER_ID_123/capture",
                            "method": "POST",
                            "rel": "capture",
                        },
                    ],
                    "status": "CREATED",
                },
                status_code=201,
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
                url=re.compile("v1/notifications/webhooks"),
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

            response = merchant_client.post(
                "/api/payment/v1/conekta_oxxo/deposit/",
                {
                    "type": const.TransactionType.DEPOSIT,
                    "amount": "100.00",
                    "currency": "USD",
                    "wallet_id": wallet_conekta_oxxo.uuid,
                    "customer_id": "customer1",
                    "user_data": UserDataFactory.build().dict(),
                    "redirect_url": "http://google.com",
                },
                format="json",
            )

            assert response.status_code == 201, response.json()
            trx = PaymentTransaction.objects.get()

            assert trx.form
            assert (
                trx.form.action_url
                == "https://www.sandbox.paypal.com/checkoutnow?token=ORDER_ID_123"
            )
            response = merchant_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json()["form"] == {
                "action_url": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER_ID_123",
                "fields": {},
                "method": "get",
            }

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

            trx.refresh_from_db()
            assert trx.extra.get("is_finalization_performed") is True

    @pytest.mark.parametrize(
        "expected_status, paypal_status",
        [
            (entities.TransactionStatus.SUCCESS, "COMPLETED"),
            (entities.TransactionStatus.PENDING, "CREATED"),
            (entities.TransactionStatus.REFUNDED, "VOIDED"),
        ],
    )
    def test_deposit_success(self, wallet_conekta_oxxo, expected_status, paypal_status):
        """
        This test verifies the status of a deposit transaction using PayPal.
        After calling the PayPal client to check the transaction status,
        the test asserts that the transaction is marked as successful/created/voided.
        """
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

            m.get(
                url=re.compile("/v2/checkout/orders/ORDER_ID_123"),
                json={
                    "id": "ORDER_ID_123",
                    "status": paypal_status,
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "captureID",
                                        "status": paypal_status,
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

            client = PaypalClient(trx_id=trx.id)
            status = client.get_transaction_status()
            assert not isinstance(status, errors.Error)

            assert status.operation_status == expected_status
            assert status.remote_amount
            assert status.remote_amount.value == Decimal("100.00")
            assert status.remote_amount.currency == "USD"

    def test_withdraw_success(
        self, merchant_client, currency_wallet_paypal, mock_on_commit
    ):
        """
        Test  the successful withdrawal process using PayPal.
        - Creates a wallet for the user in the PayPal IE system.
        - Simulates a withdrawal request and verifies that the response indicates
        a successful transaction.
        - Asserts that the transaction status is marked as 'success'.
        """
        with requests_mock.Mocker() as m:
            m.post(
                url=re.compile("/v1/oauth2/token"),
                json={
                    "expires_in": 100,
                    "access_token": "token",
                },
            )
            m.post(
                url=re.compile("/v1/payments/payouts"),
                json={
                    "batch_header": {
                        "payout_batch_id": "123",
                    },
                },
            )

            response = merchant_client.post(
                "/api/payment/v1/paypal/withdraw/",
                {
                    "amount": "43.00",
                    "currency": "USD",
                    "wallet_id": currency_wallet_paypal.wallet.uuid,
                    "customer_id": "customer1",
                    "user_data": UserDataFactory.build().dict(),
                    "withdraw_to_account": "123123",
                },
                format="json",
            )
            assert response.status_code == 201, response.content
            trx: PaymentTransaction = PaymentTransaction.objects.get()

            assert trx.user_data
            assert trx.user_data.model_dump() == {
                "address": "Lenina 1",
                "city": "Taraz",
                "country": "Kazakhstan",
                "email": "test@test.com",
                "first_name": "John",
                "last_name": "Doe",
                "phone": "+1234567890",
                "post_code": "123456",
                "state": "Zhambyl",
            }
            assert trx.withdraw_to_account == "123123"
            assert trx.id_in_payment_system == "123"

            m.get(
                url=re.compile("/v1/payments/payouts/.*"),
                json={
                    "batch_header": {
                        "batch_status": "SUCCESS",
                        "amount": {
                            "currency": trx.currency,
                            "value": str(trx.amount),
                        },
                        "payout_batch_id": "123",
                    },
                },
            )
            m.post("https://callbacks/", json={})

            trx.wallet.refresh_from_db()
            assert trx.wallet.balance == Decimal("57.00")
            assert trx.wallet.hold_balance == Decimal("43.00")

            tasks.check_status(trx.id)

            trx.refresh_from_db()
            assert trx.status == entities.TransactionStatus.SUCCESS
            trx.wallet.refresh_from_db()
            assert trx.wallet.balance == Decimal("57.00")
            assert trx.wallet.hold_balance == Decimal("0.00")

            assert trx.outcomingcallback_set.count() == 1
            cb = trx.outcomingcallback_set.get()
            assert cb.status == const.CallbackStatus.SUCCESS
            assert cb.body == matchers.DictContains(
                {
                    "amount": "43.00",
                    "currency": "USD",
                    "type": "withdrawal",
                    "created_at": mock.ANY,
                    "id": mock.ANY,
                    "status": "success",
                    "updated_at": mock.ANY,
                    "wallet_id": str(trx.wallet.wallet.uuid),
                    "form": None,
                    "user_data": {
                        "address": "Lenina 1",
                        "city": "Taraz",
                        "country": "Kazakhstan",
                        "email": "test@test.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "phone": "+1234567890",
                        "post_code": "123456",
                        "state": "Zhambyl",
                    },
                }
            )

            # Check logs
            assert list(
                trx.paymenttransactioneventlog_set.order_by("id").values(
                    "event_type",
                    "description",
                )
            ) == [
                {
                    "description": "POST https://api-m.sandbox.paypal.com/v1/oauth2/token",
                    "event_type": "external_api_request",
                },
                {
                    "description": "POST https://api-m.sandbox.paypal.com/v1/payments/payouts",
                    "event_type": "external_api_request",
                },
                {
                    "description": "POST https://api-m.sandbox.paypal.com/v1/oauth2/token",
                    "event_type": "external_api_request",
                },
                {
                    "description": "GET https://api-m.sandbox.paypal.com/v1/payments/payouts/123",
                    "event_type": "external_api_request",
                },
                {
                    "description": "Attempt to send callback: 1",
                    "event_type": "callback_sending_attempt",
                },
                {"description": "Withdrawal success", "event_type": "info"},
            ]

    def test_callback_approved(self, merchant_client, wallet_conekta_oxxo):
        """
        Tests the callback handling when a PayPal order is approved by the buyer.
        - Simulates a webhook event from PayPal indicating that the order has been approved.
        - Verifies that the system triggers the appropriate action to finalize the deposit.
        - Asserts that the callback response is successful.
        """
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
