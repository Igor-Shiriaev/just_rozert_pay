from unittest import mock
from unittest.mock import Mock, patch

from django.http import HttpResponse
from rest_framework.exceptions import ErrorDetail
from rozert_pay.common import const
from rozert_pay.payment import models
from rozert_pay.payment.models import OutcomingCallback, PaymentTransaction
from tests.payment.systems.cardpay_systems import cardpay_test_utils
from waffle.testutils import override_switch


class TestCardpayApplepayFlow:
    def test_deposit_new_flow_success(
        self,
        wallet_cardpay_applepay,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
    ):
        resp = cardpay_test_utils.make_applepay_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_applepay,
        )
        assert resp.status_code == 201
        trx = PaymentTransaction.objects.get()
        assert trx.customer_id
        assert trx.status == const.TransactionStatus.SUCCESS
        assert OutcomingCallback.objects.count() == 1
        cb = OutcomingCallback.objects.get()
        assert cb.body["form"] == {
            "action_url": "http://redirect",
            "fields": {},
            "method": "get",
        }
        assert trx.extra == {
            "encrypted_data": "some encrypted data",
            "form": {"action_url": "http://redirect", "fields": {}, "method": "get"},
            "user_data": mock.ANY,
        }

    def test_withdraw_flow_success(
        self,
        wallet_cardpay_applepay,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
    ):
        resp = cardpay_test_utils.make_applepay_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_applepay,
        )
        assert resp.status_code == 201

        trx = models.PaymentTransaction.objects.get()
        assert trx.status == const.TransactionStatus.SUCCESS

        # by card
        with override_switch(const.CARDPAY_APPLEPAY_BANKCARD_SWITCH, active=True):
            resp, m = cardpay_test_utils.make_applepay_withdraw_request(
                wallet=wallet_cardpay_applepay,
                merchant_client=merchant_client,
                amount=30,
            )
        assert resp.status_code == 201

        card_trx: PaymentTransaction | None = PaymentTransaction.objects.last()
        assert card_trx

        assert card_trx.status == const.TransactionStatus.SUCCESS

        payload = m.request_history[0].json()
        assert payload == {
            "card_account": {"recipient_info": "John Doe"},
            "customer": mock.ANY,
            "merchant_order": mock.ANY,
            "payment_data": {"id": "123"},
            "payment_method": "BANKCARD",
            "payout_data": {
                "amount": "30.00",
                "currency": "USD",
                "encrypted_data": "some encrypted data",
            },
            "request": mock.ANY,
        }

    def test_withdraw_flow_success_switch_off(
        self,
        wallet_cardpay_applepay,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
    ):
        resp = cardpay_test_utils.make_applepay_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_applepay,
        )
        assert resp.status_code == 201

        trx = models.PaymentTransaction.objects.get()
        assert trx.status == const.TransactionStatus.SUCCESS

        with override_switch(const.CARDPAY_APPLEPAY_BANKCARD_SWITCH, active=False):
            resp, m = cardpay_test_utils.make_applepay_withdraw_request(
                wallet=wallet_cardpay_applepay,
                merchant_client=merchant_client,
                amount=30,
            )
        assert resp.status_code == 201

        card_trx: PaymentTransaction | None = PaymentTransaction.objects.last()
        assert card_trx

        assert card_trx.status == const.TransactionStatus.SUCCESS

        assert m.request_history[0].json() == {
            "customer": mock.ANY,
            "merchant_order": mock.ANY,
            "payment_data": {"id": "123"},
            "payment_method": "APPLEPAY",
            "payout_data": {
                "amount": "30.00",
                "currency": "USD",
                "encrypted_data": "some encrypted data",
            },
            "request": mock.ANY,
        }

    def test_applepay_merchant_validation(
        self,
        wallet_cardpay_applepay,
        merchant_client,
    ):
        resp = merchant_client.post(
            f"/api/payment/v1/cardpay-applepay/merchant_validation/?wallet_id={wallet_cardpay_applepay.uuid}",
            {},
        )
        assert resp.status_code == 400
        assert resp.data == {
            "merchant_identifier": [
                ErrorDetail(string="This field is required.", code="required")
            ],
            "domain": [ErrorDetail(string="This field is required.", code="required")],
            "validation_url": [
                ErrorDetail(string="This field is required.", code="required")
            ],
            "wallet_id": [
                ErrorDetail(string="This field is required.", code="required")
            ],
        }

        # success
        with patch("requests.post") as post_mck:
            post_mck.return_value = Mock(
                json=Mock(
                    return_value={
                        "status": "success",
                    }
                ),
                text="response",
                status_code=200,
            )
            http_resp: HttpResponse = merchant_client.post(
                f"/api/payment/v1/cardpay-applepay/merchant_validation/?wallet_id={wallet_cardpay_applepay.uuid}",
                {
                    "merchant_identifier": "merchant.com.betmaster",
                    "domain": "https://betmaster.com",
                    "validation_url": "http://google.com",
                    "wallet_id": wallet_cardpay_applepay.uuid,
                },
            )
            assert http_resp.status_code == 200
            assert http_resp.content == b"response"
