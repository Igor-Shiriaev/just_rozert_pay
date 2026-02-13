from unittest.mock import Mock, call

import pytest
import requests_mock
from rozert_pay.common import const
from rozert_pay.common.const import CallbackStatus
from rozert_pay.payment import tasks
from rozert_pay.payment.models import OutcomingCallback
from rozert_pay.payment.services import outcoming_callbacks
from rozert_pay_shared.rozert_client import RozertClient
from tests.factories import OutcomingCallbackFactory

verify_callback_signature = RozertClient.verify_callback_signature


@pytest.mark.django_db
class TestOutcomingCallbacks:
    def test_signature(self):
        cb: OutcomingCallback = OutcomingCallbackFactory.create(
            target="http://api/api/payment/v2/rozert_cardpay_applepay/callback?transaction_uuid=5ce910e2-2e42-443f-945c-21317461923a",
            status=CallbackStatus.PENDING,
            body={
                "id": "710b0eee-58ab-4844-adb5-6a6bf8f2c0d9",
                "form": None,
                "type": "deposit",
                "amount": "1.00",
                "status": "charged_back",
                "currency": "EUR",
                "user_data": {
                    "city": "Tallinn",
                    "email": "anastassia.m@betmaster.com",
                    "phone": "+37255554444",
                    "state": None,
                    "address": "tuukri 23",
                    "country": "EE",
                    "language": "ru",
                    "last_name": "Malova",
                    "post_code": "123123123",
                    "first_name": "Anastassia",
                },
                "wallet_id": "b9914210-b79e-4dcb-8ee2-bada2383f0f7",
                "card_token": None,
                "created_at": "2025-08-29T06:27:22.230852Z",
                "updated_at": "2025-08-29T06:38:09.968006Z",
                "customer_id": "b21a9867-b317-4374-b984-250d62484ad4",
                "instruction": None,
                "callback_url": "https://betmaster.ee/api/payment/v2/rozert_cardpay_applepay/callback?transaction_uuid=5ce910e2-2e42-443f-945c-21317461923a",
                "decline_code": None,
                "decline_reason": None,
                "external_account_id": None,
                "external_customer_id": "dcb461c7-3549-4ff5-93bd-13b63ec11e2c",
            },
        )

        with requests_mock.Mocker() as m:
            m.post("http://api/api/payment/v2/rozert_cardpay_applepay/callback")
            tasks.send_callback(callback_id=str(cb.id))

            signature = m.last_request.headers["X-Signature"]
            assert signature
            assert verify_callback_signature(
                body=m.last_request.body.decode(),
                signature=signature,
                secret_key=cb.transaction.wallet.wallet.merchant.secret_key,
            )
            assert not verify_callback_signature(
                body=m.last_request.body.decode() + "123",
                signature=signature,
                secret_key=cb.transaction.wallet.wallet.merchant.secret_key,
            )
            assert not verify_callback_signature(
                body=m.last_request.body.decode(),
                signature=signature + "123",
                secret_key=cb.transaction.wallet.wallet.merchant.secret_key,
            )
            assert not verify_callback_signature(
                body=m.last_request.body.decode(),
                signature=signature,
                secret_key=cb.transaction.wallet.wallet.merchant.secret_key + "123",
            )

        cb.refresh_from_db()
        assert cb.status == CallbackStatus.SUCCESS

    def test_retry(self):
        cb: OutcomingCallback = OutcomingCallbackFactory.create(
            target="http://example",
        )

        spy = Mock()

        def run():
            with requests_mock.Mocker() as m:
                m.post("http://example/", json={"status": "success"})
                outcoming_callbacks.retry_outcoming_callback(
                    item_or_qs=cb,
                    action_user=None,
                    message_user=spy,
                )
            cb.refresh_from_db()

        run()
        assert spy.call_args == call(
            "Callbacks are queued for retry: retried = 0, skipped because status success = 1"
        )

        cb.status = const.CallbackStatus.PENDING
        cb.save()

        run()
        assert spy.call_args == call(
            "Callbacks are queued for retry: retried = 1, skipped because status success = 0"
        )
        assert cb.logs
        assert 'Response: 200 {"status": "success"}' in cb.logs
        assert cb.status == const.CallbackStatus.SUCCESS
