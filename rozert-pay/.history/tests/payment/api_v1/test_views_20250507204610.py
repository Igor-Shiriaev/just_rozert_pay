from unittest import mock
from uuid import uuid4

import pytest
from django.urls import reverse
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APIClient
from rozert_pay.common.authorization import AuthData
from rozert_pay.common.const import TransactionStatus, TransactionType
from rozert_pay.common.types import to_any
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.models import Merchant, PaymentTransaction, Wallet
from tests.factories import (CurrencyWalletFactory, PaymentTransactionFactory,
                             WalletFactory)
from tests.payment.api_v1 import matchers


def force_authenticate(client: APIClient, merchant: Merchant):
    client.force_authenticate(
        user=merchant.merchant_group.user, token=to_any(AuthData(merchant))
    )


class TestWalletView:
    def test_returns_data_for_current_user(self, api_client, db):
        w1 = WalletFactory.create()
        WalletFactory.create()

        CurrencyWalletFactory.create(
            wallet=w1,
        )

        force_authenticate(api_client, w1.merchant)
        url = reverse("wallet-list")
        response = api_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data == [
            {
                "id": mock.ANY,
                "created_at": mock.ANY,
                "updated_at": mock.ANY,
                "balances": [{"currency": "USD", "balance": "100.00"}],
            }
        ]


class TestTransactionViewSet:
    url = reverse("transaction-list")

    def test_returns_data_for_current_user(self, api_client, db):
        t1 = PaymentTransactionFactory.create()
        PaymentTransactionFactory.create()

        force_authenticate(api_client, t1.wallet.wallet.merchant)
        url = reverse("transaction-list")
        response = api_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1
        assert list(response.data) == [
            {
                "id": mock.ANY,
                "wallet_id": mock.ANY,
                "type": TransactionType.DEPOSIT,
                "amount": "100.00",
                "currency": "USD",
                "form": None,
                "user_data": None,
                "status": TransactionStatus.PENDING,
                "customer_id": None,
                "deposit_account": None,
                "external_account_id": None,
                "decline_code": None,
                "decline_reason": None,
                "created_at": mock.ANY,
                "updated_at": mock.ANY,
                "instruction": None,
                "callback_url": mock.ANY,
            }
        ]

    GOOD_WALLET_UUID = str(uuid4())
    BAD_WALLET_UUID = str(uuid4())

    @pytest.mark.parametrize(
        "payload,error",
        [
            [
                {},
                {
                    "amount": [
                        ErrorDetail(string="This field is required.", code="required")
                    ],
                    "currency": [
                        ErrorDetail(string="This field is required.", code="required")
                    ],
                    "wallet_id": [
                        ErrorDetail(string="This field is required.", code="required")
                    ],
                },
            ],
            [
                {
                    "wallet_id": GOOD_WALLET_UUID[:-1] + "1",
                    "type": TransactionType.WITHDRAWAL,
                    "amount": "100.00",
                    "currency": "USD",
                },
                {"wallet_id": [ErrorDetail(string="Wallet not found", code="invalid")]},
            ],
            [
                {
                    "wallet_id": BAD_WALLET_UUID,
                    "type": TransactionType.WITHDRAWAL,
                    "amount": "100.00",
                    "currency": "USD",
                },
                {"wallet_id": [ErrorDetail(string="Wallet not found", code="invalid")]},
            ],
            [
                {
                    "type": TransactionType.DEPOSIT,
                    "amount": "0",
                    "currency": "USD",
                    "wallet_id": GOOD_WALLET_UUID,
                },
                {
                    "amount": [
                        ErrorDetail(
                            string="Amount must be greater than 0.", code="invalid"
                        )
                    ]
                },
            ],
        ],
    )
    def test_deposit_validation(
        self, api_client, db, merchant, payload, error
    ):
        wallet = WalletFactory.create(
            merchant=merchant,
            uuid=self.GOOD_WALLET_UUID,
        )
        CurrencyWalletFactory.create(
            wallet=wallet,
            balance=100,
            currency="USD",
        )

        WalletFactory.create(
            uuid=self.BAD_WALLET_UUID,
        )

        force_authenticate(api_client, merchant)
        response = api_client.post(self.url, payload)
        assert response.status_code == 400
        assert response.data == error

    @pytest.mark.parametrize(
        "payload,error",
        [
            [
                {
                    "type": TransactionType.WITHDRAWAL,
                    "wallet_id": GOOD_WALLET_UUID,
                    "amount": "101.00",
                    "currency": "EUR",
                    "withdraw_to_account": "1234567890",
                },
                {"amount": [ErrorDetail(string="Insufficient funds.", code="invalid")]},
            ],
            [
                {
                    "wallet_id": GOOD_WALLET_UUID[:-1] + "1",
                    "type": TransactionType.WITHDRAWAL,
                    "amount": "100.00",
                    "currency": "USD",
                    "withdraw_to_account": "1234567890",
                },
                {"wallet_id": [ErrorDetail(string="Wallet not found", code="invalid")]},
            ],
            [
                {
                    "wallet_id": BAD_WALLET_UUID,
                    "type": TransactionType.WITHDRAWAL,
                    "amount": "100.00",
                    "currency": "USD",
                    "withdraw_to_account": "1234567890",
                },
                {"wallet_id": [ErrorDetail(string="Wallet not found", code="invalid")]},
            ],
        ],
    )
    def test_payout_validation(
        self, api_client, db, merchant, payload, error, disable_error_logs
    ):
        wallet = WalletFactory.create(
            merchant=merchant,
            uuid=self.GOOD_WALLET_UUID,
        )
        CurrencyWalletFactory.create(
            wallet=wallet,
            balance=100,
            currency="USD",
        )

        WalletFactory.create(
            uuid=self.BAD_WALLET_UUID,
        )

        s = serializers.WithdrawalTransactionRequestSerializer(
            data=payload,
            context={"merchant": merchant},
        )
        assert not s.is_valid()
        assert s.errors == error

    def test_deposit_transaction_created(
        self,
        api_client,
        db,
        merchant,
        wallet,
        disable_celery_task,
        disable_error_logs,
    ):
        force_authenticate(api_client, merchant)

        response = api_client.post(
            self.url,
            {
                "type": TransactionType.DEPOSIT,
                "amount": "100.00",
                "currency": "USD",
                "wallet_id": wallet.uuid,
            },
        )

        assert response.status_code == 201, response.data
        assert response.data == matchers.DictContains(
            {
                "id": mock.ANY,
                "wallet_id": mock.ANY,
                "type": TransactionType.DEPOSIT,
                "amount": "100.00",
                "currency": "USD",
                "status": "pending",
                "customer_id": None,
                "deposit_account": None,
                "external_account_id": None,
            }
        )

        trx = PaymentTransaction.objects.get()
        assert trx.amount == 100
        assert trx.wallet.wallet.merchant == merchant
        assert trx.wallet.currency == "USD"
        assert trx.wallet.balance == 0
        assert trx.type == TransactionType.DEPOSIT

        # another attempt does not creates another wallet
        response = api_client.post(
            self.url,
            {
                "type": TransactionType.DEPOSIT,
                "amount": "200.00",
                "currency": "USD",
                "wallet_id": wallet.uuid,
            },
        )
        assert response.status_code == 201
        assert PaymentTransaction.objects.count() == 2
        assert Wallet.objects.count() == 1

        trx = PaymentTransaction.objects.get(uuid=response.data["id"])
        assert trx.amount == 200
        assert trx.wallet.wallet.merchant == merchant
        assert trx.wallet.currency == "USD"
        assert trx.wallet.balance == 0
