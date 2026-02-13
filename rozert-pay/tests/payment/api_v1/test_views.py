from decimal import Decimal
from unittest import mock
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APIClient
from rozert_pay.account.models import User
from rozert_pay.common.authorization import AuthData
from rozert_pay.common.const import TransactionStatus, TransactionType
from rozert_pay.common.types import to_any
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.models import Merchant, PaymentTransaction, Wallet
from tests.factories import (
    BitsoSpeiCardBankFactory,
    CurrencyWalletFactory,
    PaymentCardBankFactory,
    PaymentTransactionFactory,
    UserFactory,
    WalletFactory,
)
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
            operational_balance=Decimal("100.00"),
            frozen_balance=Decimal("10.00"),
            pending_balance=Decimal("20.00"),
        )

        force_authenticate(api_client, w1.merchant)
        url = reverse("wallet-list")
        response = api_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1

        expected_balance_data = {
            "currency": "USD",
            "operational_balance": "100.00",
            "frozen_balance": "10.00",
            "pending_balance": "20.00",
            "available_balance": "70.00",  # 100 - 10 - 20
        }
        assert response.data[0]["balances"][0] == expected_balance_data


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
                "card_token": None,
                "external_account_id": None,
                "decline_code": None,
                "decline_reason": None,
                "created_at": mock.ANY,
                "updated_at": mock.ANY,
                "instruction": None,
                "callback_url": mock.ANY,
                "external_customer_id": mock.ANY,
            }
        ]

    GOOD_WALLET_UUID = str(uuid4())
    BAD_WALLET_UUID = str(uuid4())

    @pytest.mark.parametrize(
        "payload_template, error",
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
            # Case 2: Invalid UUID format
            [
                {
                    "wallet_id": "INVALID_UUID",
                    "amount": "100.00",
                    "currency": "USD",
                },
                {
                    "wallet_id": [
                        ErrorDetail(string="Must be a valid UUID.", code="invalid")
                    ]
                },
            ],
            # Case 3: Wallet not found (belongs to another merchant)
            [
                {
                    "wallet_id": "BAD_WALLET",
                    "amount": "100.00",
                    "currency": "USD",
                },
                {"wallet_id": [ErrorDetail(string="Wallet not found", code="invalid")]},
            ],
            # Case 4: Zero amount
            [
                {
                    "amount": "0",
                    "currency": "USD",
                    "wallet_id": "GOOD_WALLET",
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
        self, api_client, db, merchant, payload_template, error, disable_error_logs
    ):
        # Create all necessary wallets dynamically for this specific test run
        good_wallet = WalletFactory.create(merchant=merchant)
        bad_wallet = WalletFactory.create()  # another merchant by default

        payload = payload_template.copy()
        if payload.get("wallet_id") == "GOOD_WALLET":
            payload["wallet_id"] = str(good_wallet.uuid)
        elif payload.get("wallet_id") == "BAD_WALLET":
            payload["wallet_id"] = str(bad_wallet.uuid)
        elif payload.get("wallet_id") == "INVALID_UUID":
            payload["wallet_id"] = "not-a-valid-uuid"

        force_authenticate(api_client, merchant)
        response = api_client.post(self.url, payload)
        assert response.status_code == 400
        assert response.data == error

    @pytest.mark.parametrize(
        "payload_template, error",
        [
            # Case 1: Insufficient funds
            [
                {
                    "wallet_id": "GOOD_WALLET",
                    "amount": "101.00",
                    "currency": "USD",
                    "withdraw_to_account": "1234567890",
                },
                {"amount": [ErrorDetail(string="Insufficient funds.", code="invalid")]},
            ],
            # Case 2: Wallet not found (invalid UUID)
            [
                {
                    "wallet_id": "INVALID_UUID",
                    "amount": "100.00",
                    "currency": "USD",
                    "withdraw_to_account": "1234567890",
                },
                {
                    "wallet_id": [
                        ErrorDetail(string="Must be a valid UUID.", code="invalid")
                    ]
                },
            ],
            # Case 3: Wallet not found ( another merchant)
            [
                {
                    "wallet_id": "BAD_WALLET",
                    "amount": "100.00",
                    "currency": "USD",
                    "withdraw_to_account": "1234567890",
                },
                {"wallet_id": [ErrorDetail(string="Wallet not found", code="invalid")]},
            ],
            [
                {
                    "type": TransactionType.DEPOSIT,
                    "amount": "10.00",
                    "currency": "USD",
                    "wallet_id": GOOD_WALLET_UUID,
                    "withdraw_to_account": "1234567890",
                    "callback_url": "very bad url",
                },
                {
                    "callback_url": [
                        ErrorDetail(string="Enter a valid URL.", code="invalid")
                    ]
                },
            ],
        ],
    )
    def test_payout_validation(
        self, api_client, db, merchant, payload_template, error, disable_error_logs
    ):
        good_wallet = WalletFactory.create(merchant=merchant)
        CurrencyWalletFactory.create(
            wallet=good_wallet,
            operational_balance=100,
            currency="USD",
        )
        bad_wallet = WalletFactory.create()

        payload = payload_template.copy()
        if payload["wallet_id"] == "GOOD_WALLET":
            payload["wallet_id"] = str(good_wallet.uuid)
        elif payload["wallet_id"] == "INVALID_UUID":
            payload["wallet_id"] = "not-a-valid-uuid"
        elif payload["wallet_id"] == "BAD_WALLET":
            payload["wallet_id"] = str(bad_wallet.uuid)

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
        callback_url = "https://callback.com/notify"
        redirect_url = "https://redirect.com/done"
        response = api_client.post(
            self.url,
            {
                "type": TransactionType.DEPOSIT,
                "amount": "100.00",
                "currency": "USD",
                "wallet_id": wallet.uuid,
                "callback_url": callback_url,
                "redirect_url": redirect_url,
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
                "card_token": None,
                "external_account_id": None,
                "callback_url": callback_url,
            }
        )

        trx = PaymentTransaction.objects.get()
        assert trx.amount == 100
        assert trx.wallet.wallet.merchant == merchant
        assert trx.wallet.currency == "USD"

        # Check all new balance fields.
        assert trx.wallet.operational_balance == 0
        assert trx.wallet.frozen_balance == 0
        assert trx.wallet.pending_balance == 0

        assert trx.type == TransactionType.DEPOSIT
        assert trx.callback_url == callback_url
        assert trx.redirect_url == redirect_url

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

        # Check all new balance fields again
        assert trx.wallet.operational_balance == 0
        assert trx.wallet.frozen_balance == 0
        assert trx.wallet.pending_balance == 0


@pytest.mark.django_db
class TestCardBinDataViewSet:
    url = "/api/payment/v1/card-bin-data/"

    def test_unauthenticated_access_is_denied(self, api_client: APIClient):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @override_settings(BACK_SECRET_KEY="test-secret")
    def test_wrong_secret_key_is_denied(self, api_client: APIClient, db):
        UserFactory.create(email=settings.SYSTEM_USER_EMAIL)
        response = api_client.get(self.url, HTTP_X_BACK_SECRET_KEY="wrong-secret")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @override_settings(BACK_SECRET_KEY=None)
    def test_no_secret_key_in_settings(self, api_client: APIClient, caplog):
        UserFactory.create(email=settings.SYSTEM_USER_EMAIL)
        response = api_client.get(self.url, HTTP_X_BACK_SECRET_KEY="any-key")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "BACK_SECRET_KEY is not set" in caplog.text

    @override_settings(BACK_SECRET_KEY="test-secret")
    @pytest.mark.usefixtures("disable_error_logs")
    def test_no_system_user_configured(self, api_client: APIClient, db):
        assert not User.objects.filter(email=settings.SYSTEM_USER_EMAIL).exists()
        response = api_client.get(self.url, HTTP_X_BACK_SECRET_KEY="test-secret")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["detail"] == "System user not configured."

    @override_settings(BACK_SECRET_KEY="test-secret")
    def test_get_card_bin_data_success(self, api_client, db):
        UserFactory.create(email=settings.SYSTEM_USER_EMAIL)
        card_bank_no_bitso = PaymentCardBankFactory.create()

        card_bank_with_one_bitso = PaymentCardBankFactory.create()
        bitso_bank1 = BitsoSpeiCardBankFactory.create()
        bitso_bank1.banks.add(card_bank_with_one_bitso)

        card_bank_with_two_bitso = PaymentCardBankFactory.create()
        bitso_bank2 = BitsoSpeiCardBankFactory.create()
        bitso_bank3 = BitsoSpeiCardBankFactory.create()
        bitso_bank2.banks.add(card_bank_with_two_bitso)
        bitso_bank3.banks.add(card_bank_with_two_bitso)

        response = api_client.get(self.url, HTTP_X_BACK_SECRET_KEY="test-secret")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert isinstance(data, dict)
        results = data["results"]
        assert isinstance(results, list)
        assert len(results) == 3

        response_data_map = {item["bin"]: item for item in results}

        result_with_two_bitso = response_data_map[card_bank_with_two_bitso.bin]
        result_with_two_bitso["bitso_banks"] = sorted(
            result_with_two_bitso["bitso_banks"], key=lambda x: x["code"]
        )

        expected_bitso_banks = sorted(
            [
                {
                    "id": mock.ANY,
                    "code": bitso_bank2.code,
                    "name": bitso_bank2.name,
                    "country_code": "MX",
                    "created_at": mock.ANY,
                    "updated_at": mock.ANY,
                    "is_active": True,
                },
                {
                    "id": mock.ANY,
                    "code": bitso_bank3.code,
                    "name": bitso_bank3.name,
                    "country_code": "MX",
                    "created_at": mock.ANY,
                    "updated_at": mock.ANY,
                    "is_active": True,
                },
            ],
            key=lambda x: x["code"],
        )

        expected_structure = {
            "id": mock.ANY,
            "bin": card_bank_with_two_bitso.bin,
            "bank": {
                "id": card_bank_with_two_bitso.bank.id,
                "is_non_bank": card_bank_with_two_bitso.bank.is_non_bank,
                "name": card_bank_with_two_bitso.bank.name,
            },
            "card_type": card_bank_with_two_bitso.card_type,
            "card_class": card_bank_with_two_bitso.card_class,
            "country": card_bank_with_two_bitso.country,
            "is_virtual": card_bank_with_two_bitso.is_virtual,
            "is_prepaid": card_bank_with_two_bitso.is_prepaid,
            "raw_category": card_bank_with_two_bitso.raw_category,
            "bitso_banks": expected_bitso_banks,
            "remark": card_bank_with_two_bitso.remark,
            "updated_at": mock.ANY,
            "created_at": mock.ANY,
        }

        assert result_with_two_bitso == expected_structure

        result_with_one_bitso = response_data_map[card_bank_with_one_bitso.bin]
        assert len(result_with_one_bitso["bitso_banks"]) == 1
        assert result_with_one_bitso["bitso_banks"][0]["code"] == bitso_bank1.code

        result_no_bitso = response_data_map[card_bank_no_bitso.bin]
        assert result_no_bitso["bitso_banks"] == []

    @override_settings(BACK_SECRET_KEY="test-secret")
    def test_pagination(self, api_client: APIClient, db):
        UserFactory.create(email=settings.SYSTEM_USER_EMAIL)
        PaymentCardBankFactory.create_batch(15)  # type: ignore[attr-defined]

        # First page
        response = api_client.get(
            self.url + "?page_size=10", HTTP_X_BACK_SECRET_KEY="test-secret"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["results"]) == 10
        assert data["next"] is not None
        assert data["previous"] is None

        # Second page
        next_url = data["next"]
        response = api_client.get(next_url, HTTP_X_BACK_SECRET_KEY="test-secret")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["results"]) == 5
        assert data["next"] is None
        assert data["previous"] is not None
