from unittest import mock

import requests_mock
import xmltodict
from requests_mock import Mocker
from rest_framework.response import Response
from rest_framework.test import APIClient
from rozert_pay.common.const import (
    PaymentSystemType,
    TransactionExtraFields,
    TransactionStatus,
)
from rozert_pay.payment.models import PaymentTransaction, Wallet
from rozert_pay.payment.systems.ilixium import ilixium_client
from rozert_pay.payment.systems.ilixium.ilixium_client import IlixiumUtils
from rozert_pay.payment_audit.models.audit_item import DBAuditItem
from rozert_pay.payment_audit.tasks.audit import task_periodic_run_audit_data_collection
from tests.factories import PaymentTransactionFactory
from tests.payment.systems.ilixium import fixtures


class IlixiumTestUtils:
    last_mock: Mocker

    @classmethod
    def make_deposit(
        cls,
        wallet: Wallet,
        client: APIClient,
        customer_external_id: str = "customer",
    ) -> Response:
        with requests_mock.Mocker() as m:
            m.post(
                "https://prprocessing.ilixium.com/platform/itix/direct/auth",
                text=fixtures.AUTHORIZATION_3DS_REQUIRED_RESPONSE,
            )
            m.post(
                "https://prprocessing.ilixium.com/platform/itix/history/operations",
                text=fixtures.HISTORY_RESPONSE,
            )
            cls.last_mock = m

            return client.post(
                path="/api/payment/v1/ilixium/deposit/",
                data={
                    "wallet_id": str(wallet.uuid),
                    "amount": "100",
                    "currency": "CAD",
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
                        "phone": "123123123",
                        "first_name": "John",
                        "last_name": "Doe",
                        "post_code": 123123,
                        "city": "asdasd",
                        "country": "CAN",
                        "address": "asdasdasd",
                        "date_of_birth": "2025-01-01",
                        "ip_address": "127.0.0.1",
                        "province": "province",
                    },
                    "browser_data": {
                        "accept_header": "text/html",
                        "challenge_window_size": 4,
                        "color_depth": 48,
                        "java_enabled": False,
                        "javascript_enabled": True,
                        "language": "en",
                        "screen_height": 768,
                        "screen_width": 1024,
                        "time_difference": "+3",
                        "user_agent": "User-agent",
                    },
                    "customer_id": customer_external_id,
                },
                format="json",
            )


class TestIlixiumFlow:
    def test_signature(self):
        assert (
            ilixium_client._make_digest(
                xml_str='<?xml version="1.0" encoding="UTF-8" ?><creditRequest></creditRequest>',
                password="PASSWORD",
            )
            == "q1wwnMnCBd1wfM/9F7YLkHExhXz8olR1Nwi0APnl42qgzZgucJM+TFZq2Y648ew9/EdapUtUKitLUqZVeQaiYg=="
        )

    def test_deposit(
        self, wallet_ilixium, merchant_client: APIClient, mock_send_callback
    ):
        resp = IlixiumTestUtils.make_deposit(
            wallet=wallet_ilixium,
            client=merchant_client,
        )
        m = IlixiumTestUtils.last_mock
        assert (
            xmltodict.parse(m.request_history[0].text)["authRequest"]["customer"][
                "address"
            ]["province"]
            == "province"
        )

        assert resp.status_code == 201

        trx = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.PENDING
        assert trx.form
        assert trx.form.dict() == {
            "action_url": "https://pripframev2.ilixium.com/ipframe/web/threedsmethodcheck?ref=91403",
            "fields": {
                "MD": "YWFzZGxtMzJrbDIzam4yYmprMmgzajRoajEybDNocjk4cXc=",
                "PaReq": "RU5DT0RFRF9QQVJFUQ==",
                "TermUrl": mock.ANY,
            },
            "method": "post",
        }

        # Perform redirect
        with requests_mock.Mocker() as m:
            m.post(
                "https://prprocessing.ilixium.com/platform/itix/direct/threedcomplete",
                text=fixtures.THREEDS_COMPLETE_RESPONSE,
            )
            m.post(
                "https://prprocessing.ilixium.com/platform/itix/history/operations",
                text=fixtures.HISTORY_RESPONSE.replace(
                    "trx525", IlixiumUtils.to_merchant_ref(trx)
                ),
            )
            resp = merchant_client.post(
                f"/api/payment/v1/redirect/ilixium/?transaction_id={trx.uuid}",
                data={
                    "MD": "some md",
                    "PaRes": "some pares",
                },
            )

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS
        assert resp.status_code == 302
        assert trx.extra[TransactionExtraFields.REDIRECT_RECEIVED_DATA] == {
            "MD": "some md",
            "PaRes": "some pares",
        }

    def test_deposit_decline(
        self, wallet_ilixium, merchant_client: APIClient, mock_send_callback
    ):
        resp = IlixiumTestUtils.make_deposit(
            wallet=wallet_ilixium,
            client=merchant_client,
        )
        assert resp.status_code == 201

        trx = PaymentTransaction.objects.get()

        # Perform redirect
        with requests_mock.Mocker() as m:
            m.post(
                "https://prprocessing.ilixium.com/platform/itix/direct/threedcomplete",
                text=fixtures.THREEDS_DECLINE_RESPONSE,
            )
            resp = merchant_client.post(
                f"/api/payment/v1/redirect/ilixium/?transaction_id={trx.uuid}",
                data={
                    "MD": "some md",
                    "PaRes": "some pares",
                },
            )

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "Declined"
        assert trx.decline_reason == "Declined"

    def test_audit_items_sync_get_status(self, wallet_ilixium):
        PaymentTransactionFactory.create(id=525)

        with requests_mock.Mocker() as m:
            m.post(
                "https://prprocessing.ilixium.com/platform/itix/history/operations",
                text=fixtures.HISTORY_RESPONSE,
            )

            task_periodic_run_audit_data_collection(
                system_types=[PaymentSystemType.ILIXIUM],
            )

            assert DBAuditItem.objects.count() == 2

    def test_deposit_decline_on_auth(
        self, wallet_ilixium, merchant_client: APIClient, mock_send_callback
    ):
        # Simulate Ilixium initial auth responding with REJECTED (VB48)
        with requests_mock.Mocker() as m:
            m.post(
                "https://prprocessing.ilixium.com/platform/itix/direct/auth",
                text=fixtures.AUTHORIZATION_REJECTED_VB48_RESPONSE,
            )
            # History endpoint may still be queried by client mixins; provide a valid stub
            m.post(
                "https://prprocessing.ilixium.com/platform/ili/history/operations",
                text=fixtures.HISTORY_RESPONSE,
            )

            resp = merchant_client.post(
                path="/api/payment/v1/ilixium/deposit/",
                data={
                    "wallet_id": str(wallet_ilixium.uuid),
                    "amount": "100",
                    "currency": "CAD",
                    "redirect_url": "http://example.com",
                    "callback_url": "http://example.com",
                    "card": {
                        "card_num": "5574445651178446",
                        "card_cvv": "827",
                        "card_expiration": "08/2027",
                        "card_holder": "Card Holder",
                    },
                    "user_data": {
                        "language": "en",
                        "email": "testaccount+tobique@betmaster.com",
                        "phone": "+13122222223",
                        "first_name": "Testtob",
                        "last_name": "Biqie",
                        "post_code": "12345",
                        "city": "Cantest",
                        "country": "CA",
                        "address": "Tset",
                        "date_of_birth": "2000-02-05",
                        "ip_address": "62.112.11.40",
                        "province": "CA-BC",
                    },
                    "browser_data": {
                        "accept_header": "application/json, text/plain, */*",
                        "challenge_window_size": 4,
                        "color_depth": 48,
                        "java_enabled": False,
                        "javascript_enabled": True,
                        "language": "en",
                        "screen_height": 1200,
                        "screen_width": 1920,
                        "time_difference": "-120",
                        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
                    },
                    "customer_id": "1584bffc-a0ed-448c-a960-fae4fd4e8eed",
                },
                format="json",
            )

        # Transaction is created
        assert resp.status_code == 201
        trx = PaymentTransaction.objects.get()

        # Expect immediate failure with message from status.message
        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "Access to this functionality has been denied"
        assert trx.decline_reason == "Access to this functionality has been denied"
