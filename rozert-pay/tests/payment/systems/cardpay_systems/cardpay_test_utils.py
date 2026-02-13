import re
import typing as ty
from decimal import Decimal

import requests_mock
from rest_framework.response import Response
from rest_framework.test import APIClient
from rozert_pay.payment.models import Wallet
from tests.factories import UserDataFactory


def make_deposit_request(
    *,
    merchant_client: APIClient,
    wallet: Wallet,
    # If passed, card token will be used
    card_token: str | None = None,
    get_status_response: dict[str, ty.Any] | None = None,
    is_pending_request: bool = False,
    amount: int | Decimal = 100,
    customer_external_id: str = "customer"
) -> Response:
    with requests_mock.Mocker() as m:
        m.post(
            "https://sandbox.cardpay.com/api/auth/token",
            json={
                "expires_in": 1000,
                "refresh_expires_in": 1000,
                "access_token": "token",
            },
        )
        m.post(
            "https://sandbox.cardpay.com/api/payments",
            json={
                "redirect_url": "http://redirect",
                "payment_data": {
                    "id": "123",
                },
            },
        )
        m.get(
            re.compile("https://sandbox.cardpay.com/api/payments/"),
            json=get_status_response
            or {
                "data": [
                    {
                        "payment_data": {
                            "status": "IN_PROGRESS"
                            if is_pending_request
                            else "COMPLETED",
                            "id": "123",
                            "amount": str(amount),
                            "currency": "USD",
                        }
                    }
                ]
            },
        )

        resp = merchant_client.post(
            "/api/payment/v1/cardpay-cards/deposit/"
            if card_token is None
            else "/api/payment/v1/cardpay-cards/deposit_card_token/",
            {
                "amount": str(amount),
                "currency": "USD",
                "wallet_id": wallet.uuid,
                "customer_id": customer_external_id,
                "user_data": UserDataFactory.build(state=None).model_dump(),
                "redirect_url": "http://google.com",
                "card": {
                    "card_num": "4111111111111111",
                    "card_cvv": "123",
                    "card_expiration": "12/2026",
                    "card_holder": "Card Holder",
                }
                if card_token is None
                else {
                    "card_token": card_token,
                },
            },
            format="json",
        )
        return resp


def make_withdraw_request(
    wallet: Wallet,
    merchant_client: APIClient,
    card_token: str | None = None,
    amount: int | Decimal = 100,
    customer_external_id: str = "customer",
    user_data: dict[str, ty.Any] | None = None,
) -> Response:
    data: dict[str, ty.Any] = {
        "wallet_id": str(wallet.uuid),
        "amount": amount,
        "currency": "USD",
        "redirect_url": "http://example.com",
        "callback_url": "http://example.com",
        "customer_id": customer_external_id,
        "user_data": {
            "email": "test@test.com",
            "phone": "123123123",
        },
    }
    if user_data:
        data["user_data"] = user_data

    if card_token:
        data["card"] = {"card_token": str(card_token)}
        url = "/api/payment/v1/cardpay-cards/withdraw/card-token/"
    else:
        url = "/api/payment/v1/cardpay-cards/withdraw/card-data/"
        data["card"] = {
            "card_num": "4111111111111111",
            "card_cvv": "123",
            "card_expiration": "12/2026",
            "card_holder": "Card Holder",
        }

    with requests_mock.Mocker() as m:
        m.post(
            "https://sandbox.cardpay.com/api/auth/token",
            json={
                "expires_in": 1000,
                "refresh_expires_in": 1000,
                "access_token": "token",
            },
        )
        m.post(
            "https://sandbox.cardpay.com/api/payouts",
            json={
                "payout_data": {
                    "id": "456",
                    "status": "COMPLETED",
                },
            },
        )
        m.get(
            re.compile("https://sandbox.cardpay.com/api/payouts/"),
            json={
                "data": [
                    {
                        "payout_data": {
                            "status": "COMPLETED",
                            "id": "456",
                            "amount": amount,
                            "currency": "USD",
                        }
                    }
                ]
            },
        )
        # Инициирование депозита
        response = merchant_client.post(
            url,
            data=data,
            format="json",
        )

    return response  # type: ignore[return-value]


def make_applepay_deposit_request(
    *,
    merchant_client: APIClient,
    wallet: Wallet,
    get_status_response: dict[str, ty.Any] | None = None,
    is_pending_request: bool = False,
    amount: int | Decimal = 100,
    customer_external_id: str = "customer"
) -> Response:
    with requests_mock.Mocker() as m:
        m.post(
            "https://sandbox.cardpay.com/api/auth/token",
            json={
                "expires_in": 1000,
                "refresh_expires_in": 1000,
                "access_token": "token",
            },
        )
        m.post(
            "https://sandbox.cardpay.com/api/payments",
            json={
                "redirect_url": "http://redirect",
                "payment_data": {
                    "id": "123",
                },
            },
        )
        m.get(
            re.compile("https://sandbox.cardpay.com/api/payments/"),
            json=get_status_response
            or {
                "data": [
                    {
                        "payment_data": {
                            "status": "IN_PROGRESS"
                            if is_pending_request
                            else "COMPLETED",
                            "id": "123",
                            "amount": str(amount),
                            "currency": "USD",
                        }
                    }
                ]
            },
        )

        resp = merchant_client.post(
            "/api/payment/v1/cardpay-applepay/deposit/",
            {
                "amount": str(amount),
                "currency": "USD",
                "wallet_id": wallet.uuid,
                "customer_id": customer_external_id,
                "user_data": UserDataFactory.build(state=None).model_dump(),
                "redirect_url": "http://google.com",
                "encrypted_data": "some encrypted data",
            },
            format="json",
        )
        return resp


def make_applepay_withdraw_request(
    wallet: Wallet,
    merchant_client: APIClient,
    amount: int | Decimal = 100,
    customer_external_id: str = "customer",
) -> tuple[Response, requests_mock.Mocker]:
    data: dict[str, ty.Any] = {
        "wallet_id": str(wallet.uuid),
        "amount": amount,
        "currency": "USD",
        "redirect_url": "http://example.com",
        "callback_url": "http://example.com",
        "customer_id": customer_external_id,
        "encrypted_data": "some encrypted data",
    }

    with requests_mock.Mocker() as m:
        m.post(
            "https://sandbox.cardpay.com/api/auth/token",
            json={
                "expires_in": 1000,
                "refresh_expires_in": 1000,
                "access_token": "token",
            },
        )
        m.post(
            "https://sandbox.cardpay.com/api/payouts",
            json={
                "payout_data": {
                    "id": "456",
                    "status": "COMPLETED",
                },
            },
        )
        m.get(
            re.compile("https://sandbox.cardpay.com/api/payouts/"),
            json={
                "data": [
                    {
                        "payout_data": {
                            "status": "COMPLETED",
                            "id": "456",
                            "amount": amount,
                            "currency": "USD",
                        }
                    }
                ]
            },
        )
        # Инициирование депозита
        response = merchant_client.post(
            "/api/payment/v1/cardpay-applepay/withdraw/",
            data=data,
            format="json",
        )

    return response, m
