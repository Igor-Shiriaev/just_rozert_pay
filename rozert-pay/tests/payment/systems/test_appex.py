import contextlib
import json
import re
import typing as ty
from decimal import Decimal
from typing import Literal, Optional
from unittest.mock import Mock, patch

import pytest
import requests_mock
from django.test import Client
from django.utils.http import urlencode
from pydantic import BaseModel
from rest_framework.response import Response
from rozert_pay.common.const import (
    CallbackStatus,
    PaymentSystemType,
    TransactionExtraFields,
    TransactionStatus,
    TransactionType,
)
from rozert_pay.payment import tasks
from rozert_pay.payment.entities import CardData
from rozert_pay.payment.models import (
    IncomingCallback,
    OutcomingCallback,
    PaymentTransaction,
    Wallet,
)
from rozert_pay.payment.services import db_services, transaction_processing
from rozert_pay.payment.systems.appex.appex_controller import appex_controller
from tests.factories import (
    CurrencyWalletFactory,
    PaymentTransactionFactory,
    WalletFactory,
)
from tests.payment.api_v1 import matchers

CARD = {
    "expires": "12/2021",
    "num": "4111111111111111",
    "cvv": "123",
    "holder": "IVAN IVANOV",
}

CARD_DATA = CardData(
    card_num="4111111111111111",  # type: ignore[arg-type]
    card_holder="SALAM 228",
    card_expiration="08/2030",
    card_cvv="123",  # type: ignore[arg-type]
)


class MockBehaviorContainer(BaseModel):
    behavior: Literal[
        "deposit_success",
        "withdraw_success",
        "withdraw_decline",
        "withdraw_error",
    ] = "deposit_success"
    decline_code: str = "DECLINE_CODE"
    deposit_response: Optional[dict[str, ty.Any]] = None
    withdraw_response: Optional[dict[str, ty.Any]] = None
    pares_response: Optional[dict[str, ty.Any]] = None
    status_response: Optional[dict[str, ty.Any]] = None
    get_merchant_wallet_balance_response: Optional[dict[str, ty.Any]] = None


@contextlib.contextmanager
def mock_requests(
    behavior_container=MockBehaviorContainer(),
):
    with requests_mock.Mocker() as m:

        def _deposit_request(*a, **k):
            if behavior_container.deposit_response:
                return json.dumps(behavior_container.deposit_response)

            if behavior_container.behavior == "deposit_success":
                return json.dumps(
                    {
                        "status": "wait",
                        "transID": "230016645",
                        "number": "1aebd9846a944c35abd1e49a85575154",
                        "ACSURL": "https://fin.4g12hs.com/api/payment/pareq",
                        "PaReq": "ODQ5NTY0OTEz",
                        "MD": "MD##285688504",
                        "TermUrl": "https://fin.4g12hs.com/api/payment/aconclude/285688504",
                    }
                )
            else:
                return json.dumps(
                    {
                        "number": "b7a930756d4740cdaa2d13fbd74e5fba",
                        "status": "error",
                        "transID": "203023128",
                        "errorcode": "127",
                        "errortext": "Payment system error",
                    }
                )

        def _withdraw_request(*a, **k):
            if behavior_container.withdraw_response:
                return json.dumps(behavior_container.withdraw_response)

            if behavior_container.behavior == "withdraw_success":
                return json.dumps(
                    {
                        "number": "e7347c19785f4179aa0b4767838c9fdf",
                        "status": "wait",
                        "transID": "203023128",
                    }
                )
            elif behavior_container.behavior == "withdraw_decline":
                return json.dumps(
                    {
                        "amount": "6000.00",
                        "amountcurr": "RUB",
                        "currency": "MBC",
                        "datetime": "2020-05-27T12:28:38+03:00",
                        "errorcode": "125",
                        "errortext": "Payment system error",
                        "number": "e7347c19785f4179aa0b4767838c9fdf",
                        "status": "error",
                        "transID": "203023128",
                    }
                )
            elif behavior_container.behavior == "withdraw_error":
                return json.dumps(
                    {
                        "number": "b7a930756d4740cdaa2d13fbd74e5fba",
                        "status": "error",
                        "transID": "203023128",
                        "errorcode": "127",
                        "errortext": "Payment system error",
                    }
                )
            else:
                return json.dumps(
                    {
                        "number": "b7a930756d4740cdaa2d13fbd74e5fba",
                        "status": "error",
                        "transID": "203023128",
                        "errorcode": "127",
                        "errortext": "Payment system error",
                    }
                )

        def _get_status(*a, **k):
            if behavior_container.status_response:
                return json.dumps(behavior_container.status_response)

            return json.dumps(
                {
                    "status": "OK",
                    "transID": "230016645",
                    "amount": "6000.00",
                    "amountcurr": "USD",
                }
            )

        def _pares(*a, **k):
            return behavior_container.pares_response or {
                "status": "OK",
                "transID": "230016645",
                "time": "2023-08-11T04:19:07+03:00",
                "number": "28c230e260e14993864c8c4cde061992",
                "PAN": "",
                "cardholder": "",
                "cardtype": None,
            }

        def _get_balance(*a, **k):
            return behavior_container.get_merchant_wallet_balance_response

        m.post(
            url=re.compile(".*/api/payment/execute"),
            text=_deposit_request,
        )
        m.post(
            url=re.compile(".*/api/payout/execute"),
            text=_withdraw_request,
        )
        m.post(
            url=re.compile(".*/api/payment/operate"),
            text=_get_status,
        )
        m.post(
            url=re.compile(".*/api/payout/status"),
            text=_get_status,
        )
        m.post(
            url=re.compile(".*/api/payment/pares"),
            json=_pares,
        )
        m.post(
            url=re.compile(".*/api/payout/balance"),
            json=_get_balance,
        )
        m.post(
            url=re.compile("/api/notify/single"),
            text="",
        )
        yield m


@pytest.mark.django_db
class TestAppexFlow:
    def test_cards_deposit_with_v1_callback(
        self,
        merchant_client,
        wallet_appex,
        mock_final_status_validation,
        mock_on_commit,
    ):
        with requests_mock.Mocker() as m:
            m.post("http://example.com/", json={})
            m.post(
                url=re.compile(".*/api/payment/execute"),
                json={
                    "status": "wait",
                    "transID": "230016645",
                    "number": "1aebd9846a944c35abd1e49a85575154",
                    "ACSURL": "https://fin.4g12hs.com/api/payment/pareq",
                    "PaReq": "ODQ5NTY0OTEz",
                    "MD": "MD##285688504",
                    "TermUrl": "https://fin.4g12hs.com/api/payment/aconclude/285688504",
                },
            )
            m.post(
                url=re.compile(".*/api/payment/pares"),
                json={
                    "status": "OK",
                    "transID": "230016645",
                    "time": "2023-08-11T04:19:07+03:00",
                    "number": "28c230e260e14993864c8c4cde061992",
                    "PAN": "",
                    "cardholder": "",
                    "cardtype": None,
                },
            )
            m.post(
                url="http://appex/api/payment/operate",
                json={
                    "status": "OK",
                    "transID": "230016645",
                    "amount": "100.00",
                    "amountcurr": "USD",
                },
            )
            response = appex_initiate_deposit(wallet_appex, merchant_client)
            assert response.status_code == 201

            trx: PaymentTransaction = PaymentTransaction.objects.get()

            # Ask for status
            resp = merchant_client.get(f"/api/payment/v1/transaction/{trx.uuid}/")
            assert resp.status_code == 200
            assert resp.json()["form"] == {
                "action_url": "https://fin.4g12hs.com/api/payment/pareq",
                "fields": {
                    "MD": "MD##285688504",
                    "PaReq": "ODQ5NTY0OTEz",
                    "TermUrl": f"https://ps-stage.rozert.cloud/api/payment/v1/redirect/appex/?transaction_id={trx.uuid}",
                },
                "method": "post",
            }

            # Pares redirect
            resp = merchant_client.post(
                f"/api/payment/v1/redirect/appex/?transaction_id={trx.uuid}",
                data={
                    "PaRes": "PaRes",
                    "MD": "MD",
                },
                is_multipart_content=True,
            )
            assert resp.status_code == 302
            # TODO: uncomment
            # assert (
            #     resp.headers["Location"]
            #     == f"https://None/deposit/result?status=initial&transactionId={trx.uuid}&paymentSystem=appex"
            # )

            # Confirmation callback
            client = Client()
            with patch.object(
                appex_controller, "_is_callback_signature_valid", return_value=True
            ):
                resp = client.post(
                    "/api/payment/v1/callback/appex/",
                    data=(
                        "opertype=pay&datetime=2023-06-20+12%3A19%3A24.40604700&transID=230016645&"
                        "PANmasked=%2A%2A%2A%2A%2A%2A&account=ACC005479&amount=100.00&"
                        f"number={trx.uuid.hex}&amountcurr=RUB&"
                        "description=Order%2Bbbe3db0f-4641-4d5a-8f1b-da604819770d&"
                        "trtype=1&signature=42D2990146395723927B99A639FE3B94&"
                        "control_string=%2A%2A%2A%2A%2A%2A%3A%3Apay%3A100.00%3ARUB%3A29c39ecc968745bf85d378dea7e880ae%3A"
                        "Order%2Bbbe3db0f-4641-4d5a-8f1b-da604819770d%3A1%3AACC005479%3A230016645%3A2023-06-20+12%3A19%3A24.40"
                        "604700%3Akey1%3Akey2"
                    ),
                    content_type="application/x-www-form-urlencoded",
                )
                assert resp.status_code == 200
                assert resp.content == b"230016645"

                # Deposit success notification
                resp = client.post(
                    "/api/payment/v1/callback/appex/",
                    data=(
                        "PAN=516732******6608&amount=100.00&"
                        f"number={trx.uuid}&"
                        "operID=624877820505477872&status=OK&"
                        "trtype=1&account=ACC073810&"
                        f"transID={trx.id_in_payment_system}&cardtype=MASTERCARD&"
                        "currency=MBC&datetime=2025-05-05+15%3A09%3A38.54698600&"
                        "paytoken=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI0N2ZiMzJhNy05ODIzLWQ2ZDAtM"
                        "WEyNS1hZjAyYmMwZTQ4NzIiLCJuYmYiOjE3NDY0NDY5NDIsInBheSI6IjYyNDg3NzgyMCJ9.jX85BwBoZkYANEhrRoM-"
                        "_b88bslnsT2r3hc_-0dcb00&"
                        "payamount=9284.19&signature=6CE66485893ED93604E71271CF28A5C2&amountcurr=USD&"
                        "cardholder=Evangelos+Gkiokas&description=Order%2Beb1883a8-a3dd-40de-a3bd-0ef733b56c55&"
                        "finalamount=100.00&percentplus=0&percentminus=0"
                    ),
                    content_type="application/x-www-form-urlencoded",
                )
                assert resp.status_code == 200
                assert resp.data is None

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

            # check last callback
            cb = OutcomingCallback.objects.last()
            assert cb and cb.body and trx.customer_card and trx.customer
            assert cb.body == matchers.DictContains(
                {
                    "card_token": str(trx.customer_card.uuid),
                    "customer_id": str(trx.customer.uuid),
                }
            )

    def test_cards_deposit_no_3ds(self, merchant_client, wallet_appex):
        appex_initiate_deposit(
            wallet_appex,
            merchant_client,
            deposit_response={
                "status": "OK",
                "transID": "230016645",
                "amount": "100.00",
                "amountcurr": "USD",
            },
        )

        trx: PaymentTransaction = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.SUCCESS

    def test_deposit_new_flow_decline(self, merchant_client, wallet_appex):
        with requests_mock.Mocker() as m:
            # Настраиваем моки для случая, когда платежная система отклоняет депозит
            m.post(
                url=re.compile(".*/api/payment/execute"),
                json={
                    "status": "error",
                    "transID": "230016645",
                    "errorcode": "125",
                    "errortext": "Payment system error",
                },
            )
            m.post(
                url=re.compile(".*/api/payment/operate"),
                json={
                    "status": "error",
                    "transID": "230016645",
                    "errorcode": "125",
                    "errortext": "Payment system error",
                },
            )

            # Подготовка данных для запроса депозита
            data = {
                "wallet_id": str(wallet_appex.uuid),
                "amount": "100",
                "currency": "USD",
                "redirect_url": "http://example.com",
                "callback_url": "http://example.com",
                "card": {
                    "card_num": "4111111111111111",
                    "card_cvv": "123",
                    "card_expiration": "12/2026",
                    "card_holder": "Card Holder",
                },
                "user_data": {
                    "language": "en",
                    "email": "test@test.com",
                    "state": None,
                },
                "customer_id": "customer",
            }

            # Инициирование депозита
            response = merchant_client.post(
                "/api/payment/v1/appex/deposit/",
                data=data,
                format="json",
            )

            # Проверка, что запрос обработан успешно
            assert response.status_code == 201

            # Получаем созданную транзакцию
            trx: PaymentTransaction = PaymentTransaction.objects.get()

            # Проверяем статус транзакции и другие атрибуты
            assert trx.status == TransactionStatus.FAILED
            assert trx.decline_code == "125"
            assert trx.decline_reason == "Payment system error"

            # Проверяем ответ API статуса транзакции
            resp = merchant_client.get(f"/api/payment/v1/transaction/{trx.uuid}/")
            assert resp.status_code == 200
            response_data = resp.json()

            # Проверка свойств транзакции в ответе
            assert response_data == matchers.DictContains(
                {
                    "status": "failed",
                    "decline_code": "125",
                    "decline_reason": "Payment system error",
                }
            )

    def test_deposit_finalize(self, merchant_client, wallet_appex):
        response = appex_initiate_deposit(
            wallet_appex,
            merchant_client,
        )
        assert response.status_code == 201

        trx = PaymentTransaction.objects.get()
        assert trx.form
        assert trx.form.model_dump() == {
            "action_url": "https://fin.4g12hs.com/api/payment/pareq",
            "fields": {
                "MD": "MD##285688504",
                "PaReq": "ODQ5NTY0OTEz",
                "TermUrl": f"https://ps-stage.rozert.cloud/api/payment/v1/redirect/appex/?transaction_id={trx.uuid}",
            },
            "method": "post",
        }

        # Call redirect
        with requests_mock.Mocker() as m:
            m.post(
                "http://appex/api/payment/pares",
                json={
                    "status": "OK",
                    "transID": "230016645",
                    "time": "2023-08-11T04:19:07+03:00",
                    "number": "28c230e260e14993864c8c4cde061992",
                    "PAN": "",
                    "cardholder": "",
                    "cardtype": None,
                },
            )

            r = _send_callback(
                merchant_client,
                {
                    "PaRes": "PaRes",
                    "MD": "MD##285688504",
                },
                is_redirect=True,
                redirect_trx_uuid=str(trx.uuid),
            )
        assert r.status_code == 302
        assert r.headers["Location"] == "http://example.com"

        trx = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.SUCCESS

    def test_cards_withdraw_success(self, merchant_client, wallet_appex):
        CurrencyWalletFactory.create(
            wallet=wallet_appex,
            currency="USD",
            balance=Decimal("1000.00"),
        )

        response = appex_initiate_payout(wallet_appex, merchant_client)
        assert response.status_code == 201, response.data

        trx = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.SUCCESS

    def test_cards_withdraw_with_token(self, merchant_client, wallet_appex):
        depo = appex_initiate_deposit(wallet_appex, merchant_client)
        assert depo.status_code == 201
        trx: PaymentTransaction = PaymentTransaction.objects.get()
        assert trx and trx.customer and trx.customer_card
        assert trx.status == TransactionStatus.SUCCESS
        assert trx.customer.external_id == "customer"
        assert trx.customer == trx.customer_card.customer

        response = merchant_client.get(
            f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200
        assert response.data["card_token"] == str(trx.customer_card.uuid)

        resp = appex_initiate_payout(
            wallet_appex, merchant_client, card_token=str(trx.customer_card.uuid)
        )
        assert resp.status_code == 201, resp.data

        assert PaymentTransaction.objects.count() == 2
        payout = PaymentTransaction.objects.last()
        assert payout and payout.customer and payout.customer_card
        assert payout.customer.external_id == "customer"
        assert payout.customer_card == trx.customer_card
        assert payout.customer == trx.customer

    def test_chargeback(
        self, merchant_client, wallet_appex, mock_on_commit, mock_send_callback
    ):
        resp = appex_initiate_deposit(wallet_appex, merchant_client)
        assert resp.status_code == 201

        trx: PaymentTransaction = PaymentTransaction.objects.get()
        assert OutcomingCallback.objects.count() == 1

        assert trx.wallet.operational_balance == 100

        resp = _send_callback(
            merchant_client,
            data=urlencode(
                {
                    "amount": "100.00",
                    "amountcurr": "EUR",
                    "currency": "MBC",
                    "number": trx.uuid.hex,
                    "description": "description",
                    "trtype": "1",
                    "payamount": "9956.20",
                    "percentplus": "0",
                    "percentminus": "0",
                    "account": "ACC005479",
                    "PAN": "535142******6321",
                    "cardholder": "Foteini soultani",
                    "cardtype": "MASTERCARD",
                    "approval": "368246",
                    "paytoken": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIzOTIxNzE1Zi0yY2U3LTc1YjctYjkxNC1iNWZmYjE0MzQ4ZjciLCJuYmYiOjE3MDYzOTUzNzYsInBheSI6IjM3MDU1MzA1OCJ9.Eli-Vvk9OyrV7L5qfWo19ATAQfXS0HgVCDMNZmCDnDc",
                    "transID": "230016645",
                    "datetime": "2024-07-04 18:07:49.85379500",
                    "operID": "379975681242664960",
                    "opertype": "chargeback",
                    "chargebackamount": "100.00",
                    "finalamount": "0.00",
                    "signature": "769AA3727A5ABDC4CEB363BEC28BB349",
                }
            ),
        )

        assert resp.status_code == 200
        trx.refresh_from_db()
        assert trx.status == TransactionStatus.CHARGED_BACK
        assert OutcomingCallback.objects.count() == 1
        assert OutcomingCallback.objects.get().body == matchers.DictContains(
            {
                "status": "charged_back",
            }
        )

        response = merchant_client.get(
            f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200
        assert response.json() == matchers.DictContains(
            {
                "status": "charged_back",
            }
        )
        trx.wallet.refresh_from_db()
        assert trx.wallet.operational_balance == 0

    def test_chargeback_reversal(
        self, wallet_appex, merchant_client, mock_on_commit, mock_send_callback
    ):
        resp = appex_initiate_deposit(wallet_appex, merchant_client)
        assert resp.status_code == 201

        trx: PaymentTransaction = PaymentTransaction.objects.get()

        assert trx.wallet.operational_balance == 100

        resp = _send_callback(
            merchant_client,
            data=urlencode(
                {
                    "amount": "100.00",
                    "amountcurr": "EUR",
                    "currency": "MBC",
                    "number": trx.uuid.hex,
                    "description": "description",
                    "trtype": "1",
                    "payamount": "9956.20",
                    "percentplus": "0",
                    "percentminus": "0",
                    "account": "ACC005479",
                    "PAN": "535142******6321",
                    "cardholder": "Foteini soultani",
                    "cardtype": "MASTERCARD",
                    "approval": "368246",
                    "paytoken": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIzOTIxNzE1Zi0yY2U3LTc1YjctYjkxNC1iNWZmYjE0MzQ4ZjciLCJuYmYiOjE3MDYzOTUzNzYsInBheSI6IjM3MDU1MzA1OCJ9.Eli-Vvk9OyrV7L5qfWo19ATAQfXS0HgVCDMNZmCDnDc",
                    "transID": "230016645",
                    "datetime": "2024-07-04 18:07:49.85379500",
                    "operID": "379975681242664960",
                    "opertype": "chargeback",
                    "chargebackamount": "100.00",
                    "finalamount": "0.00",
                    "signature": "769AA3727A5ABDC4CEB363BEC28BB349",
                }
            ),
        )

        assert resp.status_code == 200
        trx.refresh_from_db()
        assert trx.status == TransactionStatus.CHARGED_BACK
        assert OutcomingCallback.objects.count() == 1
        assert OutcomingCallback.objects.get().body == matchers.DictContains(
            {
                "status": "charged_back",
            }
        )
        trx.wallet.refresh_from_db()
        assert trx.wallet.operational_balance == 0

        # Send chargeback reversal. It means chargeback has reverted -
        # transaction in success state again
        resp = _send_callback(
            merchant_client,
            data=urlencode(
                {
                    "amount": "100.00",
                    "amountcurr": "USD",
                    "currency": "MBC",
                    "number": trx.uuid.hex,
                    "description": "description",
                    "trtype": "1",
                    "status": "chargeback",
                    "payamount": "9956.20",
                    "percentplus": "0",
                    "percentminus": "0",
                    "account": "ACC005479",
                    "PAN": "535142******6321",
                    "cardholder": "Foteini soultani",
                    "cardtype": "MASTERCARD",
                    "paytoken": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIzOTIxNzE1Zi0yY2U3LTc1YjctYjkxNC1iNWZmYjE0MzQ4ZjciLCJuYmYiOjE3MDYzOTUzNzYsInBheSI6IjM3MDU1MzA1OCJ9.Eli-Vvk9OyrV7L5qfWo19ATAQfXS0HgVCDMNZmCDnDc",
                    "transID": "230016645",
                    "datetime": "2025-04-25 10:55:10.49596800",
                    "operID": "533462744490331484",
                    "opertype": "chargeback_reversal",
                    "chargebackreversalamount": "100.00",
                    "finalamount": "0.00",
                    "signature": "1BE0A35440803E7995B2E90D6120448C",
                }
            ),
        )

        assert resp.status_code == 200
        trx.refresh_from_db()
        assert trx.extra[TransactionExtraFields.IS_CHARGEBACK_RECEIVED]
        assert trx.status == TransactionStatus.SUCCESS
        trx.wallet.refresh_from_db()
        assert trx.wallet.operational_balance == 100

    def test_handle_pares_callback_and_finalization(
        self, merchant_client, wallet_appex
    ):
        appex_initiate_deposit(wallet_appex, merchant_client)

        trx: PaymentTransaction = PaymentTransaction.objects.get()

        response = merchant_client.get(
            f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200
        assert response.json() == matchers.DictContains(
            {
                "form": {
                    "action_url": "https://fin.4g12hs.com/api/payment/pareq",
                    "fields": {
                        "MD": "MD##285688504",
                        "PaReq": "ODQ5NTY0OTEz",
                        "TermUrl": f"https://ps-stage.rozert.cloud/api/payment/v1/redirect/appex/?transaction_id={trx.uuid}",
                    },
                    "method": "post",
                }
            }
        )

        with requests_mock.Mocker() as m:
            m.post(
                "http://appex/api/payment/pares",
                json={
                    "status": "OK",
                    "transID": "230016645",
                    "time": "2023-08-11T04:19:07+03:00",
                    "number": "28c230e260e14993864c8c4cde061992",
                    "PAN": "",
                    "cardholder": "",
                    "cardtype": None,
                },
            )

            resp = _send_callback(
                merchant_client,
                data={
                    "PaRes": "PaRes",
                    "MD": "MD##285688504",
                },
                is_redirect=True,
                redirect_trx_uuid=str(trx.uuid),
            )

        assert resp.status_code == 302
        assert resp.headers["Location"] == "http://example.com"

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS

    def test_signature_callback(self, merchant, api_client):
        w1 = WalletFactory.create(
            merchant=merchant,
            system__type=PaymentSystemType.APPEX,
            system__name="Appex",
            default_callback_url="https://callbacks",
            credentials={
                "secret1": "1",
                "secret2": "2",
                "account": "fake_account",
                "host": "http://appex",
                "operator": None,
            },
        )
        WalletFactory.create(
            merchant=merchant,
            system=w1.system,
            default_callback_url="https://callbacks",
            credentials={
                "secret1": "3",
                "secret2": "4",
                "account": "fake_account",
                "host": "http://appex",
                "operator": None,
            },
        )

        # cb for creds 1
        cb = {
            "amount": "100.00",
            "amountcurr": "USD",
            "currency": "MBC",
            "number": "",
            "description": "description",
            "trtype": "1",
            "status": "chargeback",
            "payamount": "9956.20",
            "percentplus": "0",
            "percentminus": "0",
            "account": "ACC005479",
            "PAN": "535142******6321",
            "cardholder": "Foteini soultani",
            "cardtype": "MASTERCARD",
            "paytoken": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIzOTIxNzE1Zi0yY2U3LTc1YjctYjkxNC1iNWZmYjE0MzQ4ZjciLCJuYmYiOjE3MDYzOTUzNzYsInBheSI6IjM3MDU1MzA1OCJ9.Eli-Vvk9OyrV7L5qfWo19ATAQfXS0HgVCDMNZmCDnDc",
            "transID": "230016645",
            "datetime": "2025-04-25 10:55:10.49596800",
            "operID": "533462744490331484",
            "opertype": "chargeback_reversal",
            "chargebackreversalamount": "100.00",
            "finalamount": "0.00",
            "signature": "A1A67D50DE51CDA9B80C96B043D0DDFE",
        }

        # cb for creds 2
        cb2 = {
            **cb,
            "signature": "BE2A7F680F01D4CFB37CE147637C9E5C",
        }

        assert appex_controller._is_callback_signature_valid(
            Mock(
                body=urlencode(cb),
                headers={},
                spec=[],
            )
        )

        assert appex_controller._is_callback_signature_valid(
            Mock(
                body=urlencode(cb2),
                headers={},
                spec=[],
            )
        )

        cb_bad = {
            **cb,
            "signature": "BAD_SIGNATURE",
        }
        assert not appex_controller._is_callback_signature_valid(
            Mock(
                body=urlencode(cb_bad),
                headers={},
                spec=[],
            )
        )

    def test_confirmation_callback(self, merchant, api_client, wallet_appex):
        PaymentTransactionFactory.create(
            wallet__wallet=wallet_appex,
            uuid="e4e0594c93e249c495d0d4e2f29075b7",
        )
        resp = _send_callback(
            client=api_client,
            data=(
                "opertype=pay&datetime=2025-05-29+16%3A00%3A42.42493900&transID=250011144&"
                "PANmasked=411111%2A%2A%2A%2A%2A%2A1111&cardholder=S+S&lang=ru&account=ACC019273&"
                "amount=112&number=e4e0594c93e249c495d0d4e2f29075b7&amountcurr=USD&"
                "description=Order%2Be4e0594c-93e2-49c4-95d0-d4e2f29075b7&trtype=1&"
                "signature=6AD8403CB4430C0FCAC819B8F72667FF&control_string=411111%2A%2A%2A%2A%2A%2A1111%3AS+S%3A"
                "pay%3A112%3AUSD%3Ae4e0594c93e249c495d0d4e2f29075b7%3AOrder%2Be4e0594c-93e2-49c4-95d0-d4e2f29075"
                "b7%3A1%3AACC019273%3A250011144%3A2025-05-29+16%3A00%3A42.42493900%3Akey1%3Akey2"
            ),
        )
        assert resp.status_code == 200
        assert resp.content == b"250011144"

    def test_withdraw_confirmation_callback(self, merchant, api_client, wallet_appex):
        PaymentTransactionFactory.create(
            wallet__wallet=wallet_appex,
            uuid="8e6b32c7136c4485aff9f30b5ce2b2da",
            type=TransactionType.WITHDRAWAL,
        )
        resp = _send_callback(
            client=api_client,
            data={
                "account": "ACC073810",
                "amount": "50.00",
                "amountcurr": "EUR",
                "operator": "0000",
                "params": "423481******1827",
                "number": "8e6b32c7136c4485aff9f30b5ce2b2da",
                "transID": "662416804",
                "transId": "662416804",
                "datetime": "2025-06-13T14:22:35+03:00",
                "signature": "E1***[28 bytes]***23",
            },
        )
        assert resp.status_code == 200
        assert resp.content == b"OK"

    def test_withdraw_synchronization(
        self, merchant, api_client, disable_error_logs, wallet_appex
    ):
        trx: "db_services.LockedTransaction" = PaymentTransactionFactory.create(
            wallet__wallet=wallet_appex,
            wallet__hold_balance=123123123,
            type=TransactionType.WITHDRAWAL,
            status=TransactionStatus.PENDING,
        )

        with requests_mock.Mocker() as m:
            m.post(
                "http://appex/api/payout/status",
                json={
                    "number": "1b83a10cdfba473eaf629fdd13a13b3f",
                    "operID": "71152672053224114",
                    "status": "error",
                    "transID": "711526720",
                    "errorcode": "315",
                    "errortext": "Not enough funds on the dealer balance",
                },
            )
            transaction_processing.schedule_periodic_status_checks(
                trx=trx,
            )
            tasks.check_pending_transaction_status()

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "315"
        assert trx.decline_reason == "Not enough funds on the dealer balance"


def appex_initiate_deposit(
    wallet_appex: Wallet,
    merchant_client: Client,
    deposit_response: dict[str, ty.Any] | None = None,
    customer_external_id: str = "customer",
) -> Response:
    data = {
        "wallet_id": str(wallet_appex.uuid),
        "amount": "100",
        "currency": "USD",
        "redirect_url": "http://example.com",
        "callback_url": "http://example.com",
        "card": {
            "card_num": "4111111111111111",
            "card_cvv": "123",
            "card_expiration": "12/2026",
            "card_holder": "Card Holder",
        },
        "user_data": {
            "language": "en",
            "email": "test@test.com",
        },
        "customer_id": customer_external_id,
    }

    with requests_mock.Mocker() as m:
        m.post(
            url=re.compile(".*/api/payment/execute"),
            json=deposit_response
            or {
                "status": "wait",
                "transID": "230016645",
                "number": "1aebd9846a944c35abd1e49a85575154",
                "ACSURL": "https://fin.4g12hs.com/api/payment/pareq",
                "PaReq": "ODQ5NTY0OTEz",
                "MD": "MD##285688504",
                "TermUrl": "https://fin.4g12hs.com/api/payment/aconclude/285688504",
            },
        )
        m.post(
            url=re.compile(".*/api/payment/operate"),
            json={
                "status": "OK",
                "transID": "230016645",
                "amount": "100.00",
                "amountcurr": "USD",
            },
        )

        # Инициирование депозита
        response = merchant_client.post(
            "/api/payment/v1/appex/deposit/",
            data=data,
            format="json",
        )
    assert response.status_code == 201
    return response  # type: ignore[return-value]


def appex_initiate_payout(
    wallet_appex: Wallet,
    merchant_client: Client,
    card_token: str | None = None,
) -> Response:
    data: dict[str, ty.Any] = {
        "wallet_id": str(wallet_appex.uuid),
        "amount": "100",
        "currency": "USD",
        "redirect_url": "http://example.com",
        "callback_url": "http://example.com",
        "customer_id": "customer",
    }
    if card_token:
        data["card"] = {"card_token": str(card_token)}
        url = "/api/payment/v1/appex/withdraw/card-token/"
    else:
        url = "/api/payment/v1/appex/withdraw/card-data/"
        data["card"] = {
            "card_num": "4111111111111111",
            "card_cvv": "123",
            "card_expiration": "12/2026",
            "card_holder": "Card Holder",
        }

    with requests_mock.Mocker() as m:
        m.post(
            "http://appex/api/payout/execute",
            json={
                "number": "e7347c19785f4179aa0b4767838c9fdf",
                "status": "wait",
                "transID": "203023128",
            },
        )
        m.post(
            "http://appex/api/payout/status",
            json={
                "status": "OK",
                "transID": "203023128",
                "amount": "100.00",
                "amountcurr": "USD",
            },
        )
        # Инициирование депозита
        response = merchant_client.post(
            url,
            data=data,
            format="json",
        )

    return response  # type: ignore[return-value]


def _send_callback(
    client: Client,
    data: str | dict[str, ty.Any],
    is_redirect: bool = False,
    redirect_trx_uuid: str | None = None,
) -> Response:
    if isinstance(data, dict):
        data = urlencode(data)

    with patch.object(
        appex_controller, "_is_callback_signature_valid", return_value=True
    ):
        if is_redirect:
            assert redirect_trx_uuid
            url = f"/api/payment/v1/redirect/appex/?transaction_id={redirect_trx_uuid}"
        else:
            url = "/api/payment/v1/callback/appex/"

        resp = client.post(
            url,
            data=data,
            content_type="application/x-www-form-urlencoded",
        )

    if not is_redirect:
        cb: IncomingCallback | None = IncomingCallback.objects.last()
        assert cb
        assert cb.status == CallbackStatus.SUCCESS, cb.error
    return resp  # type: ignore[return-value]
