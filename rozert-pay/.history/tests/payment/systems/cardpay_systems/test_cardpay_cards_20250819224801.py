from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.exceptions import ErrorDetail
from rozert_pay.common.const import (
    CallbackStatus,
    TransactionDeclineCodes,
    TransactionStatus,
)
from rozert_pay.payment import models
from rozert_pay.payment.models import (
    CustomerCard,
    IncomingCallback,
    OutcomingCallback,
    PaymentTransaction,
)
from rozert_pay.payment.services.errors import SafeFlowInterruptionError
from rozert_pay.payment.systems.cardpay_systems.base_client import _BaseCardpayClient
from rozert_pay.payment.systems.cardpay_systems.cardpay_cards.controller import (
    CardpayController,
)
from tests.payment.systems.cardpay_systems import cardpay_test_utils
from tests.payment.systems.test_appex import appex_initiate_deposit


class TestCardpayBankcardFlow:
    def test_deposit_new_flow_success(
        self,
        wallet_cardpay_cards,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
    ):
        resp = cardpay_test_utils.make_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_cards,
        )
        assert resp.status_code == 201
        trx = PaymentTransaction.objects.get()
        assert trx.customer_id
        assert trx.status == TransactionStatus.SUCCESS
        assert OutcomingCallback.objects.count() == 1
        cb = OutcomingCallback.objects.get()
        assert cb.body["form"] == {
            "action_url": "http://redirect",
            "fields": {},
            "method": "get",
        }

    def test_deposit_bound_success(
        self,
        wallet_cardpay_cards,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
    ):
        resp = cardpay_test_utils.make_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_cards,
        )
        assert resp.status_code == 201

        assert models.CustomerCard.objects.count() == 1
        trx = PaymentTransaction.objects.get()
        trx.id_in_payment_system = "zzz"
        trx.save()

        assert trx.customer_card

        resp = cardpay_test_utils.make_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_cards,
            card_token=str(trx.customer_card.uuid),
        )
        assert resp.status_code == 201
        last_trx: PaymentTransaction | None = PaymentTransaction.objects.last()

        assert last_trx
        assert OutcomingCallback.objects.count() == 2
        assert last_trx.status == TransactionStatus.SUCCESS
        assert last_trx.customer_card == trx.customer_card
        assert last_trx.customer == trx.customer

    def test_process_v2_callback(
        self,
        wallet_cardpay_cards,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
    ):
        cardpay_test_utils.make_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_cards,
            is_pending_request=True,
        )
        trx = PaymentTransaction.objects.get()

        # To fix signature
        trx.uuid = "211310ed-9214-441b-bbe4-89f107182688"
        trx.id_in_payment_system = "902393805"
        trx.save()

        resp = merchant_client.post(
            "/api/ps/cardpay-cards/",
            {
                "payment_method": "BANKCARD",
                "merchant_order": {
                    "id": str(trx.uuid),
                    "description": 'Order "ab8cff70-bfec-4fa6-9f50-d39c1b0d5d50"',
                },
                "customer": {
                    "email": "",
                },
                "payment_data": {
                    "id": "902393805",
                    "status": "DECLINED",
                    "amount": 37.0,
                    "currency": "EUR",
                    "decline_reason": "Bank's malfunction",
                    "decline_code": "17",
                },
                "card_account": {
                    "masked_pan": "416598...4560",
                    "issuing_country_code": "CY",
                    "holder": "MR CARDHOLDER",
                    "expiration": "12/2025",
                },
            },
            format="json",
            HTTP_SIGNATURE="187b1a7ba6600243e929fa35c8a302f356e6c9319e8effbdf9944a5d11668854a9d9dca987b63e4d487367558df44a9219658fb59f668b083a484ee725ac22a5",
        )
        assert resp.status_code == 200

        cb = IncomingCallback.objects.get()
        assert cb.status == CallbackStatus.SUCCESS, cb.error
        assert cb.transaction == trx

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "17"
        assert trx.decline_reason == "Bank's malfunction"

    def test_deposit_new_flow_decline(
        self,
        wallet_cardpay_cards,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
    ):
        resp = cardpay_test_utils.make_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_cards,
            get_status_response={
                "data": [
                    {
                        "payment_data": {
                            "status": "DECLINED",
                            "id": "123",
                            "amount": "100",
                            "currency": "USD",
                            "decline_code": "123",
                            "decline_reason": "asd",
                        }
                    }
                ]
            },
        )
        assert resp.status_code == 201
        trx = PaymentTransaction.objects.get()
        assert trx.customer_id
        assert trx.status == TransactionStatus.FAILED
        assert OutcomingCallback.objects.count() == 1
        cb = OutcomingCallback.objects.get()
        assert cb.body["decline_code"] == "123"
        assert cb.body["decline_reason"] == "asd"

    def test_withdraw_flow_success(
        self,
        wallet_cardpay_cards,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
    ):
        resp = cardpay_test_utils.make_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_cards,
        )
        assert resp.status_code == 201

        trx = models.PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.SUCCESS

        trx.id_in_payment_system = None
        trx.save()

        # by card
        resp = cardpay_test_utils.make_withdraw_request(
            wallet=wallet_cardpay_cards,
            merchant_client=merchant_client,
            amount=30,
            user_data={
                "email": "test@test.com",
                "phone": "123123123",
            },
        )
        assert resp.status_code == 201, resp.data

        card_trx: PaymentTransaction | None = PaymentTransaction.objects.last()
        assert card_trx
        assert card_trx.extra == {
            "user_data": {
                "address": None,
                "city": None,
                "country": None,
                "email": "test@test.com",
                "first_name": None,
                "language": None,
                "last_name": None,
                "phone": "123123123",
                "post_code": None,
                "state": None,
            }
        }

        assert card_trx.status == TransactionStatus.SUCCESS
        card_trx.id_in_payment_system = None
        card_trx.save()

        # by card token
        assert trx.customer_card
        resp = cardpay_test_utils.make_withdraw_request(
            wallet=wallet_cardpay_cards,
            merchant_client=merchant_client,
            card_token=str(trx.customer_card.uuid),
            amount=30,
        )
        assert resp.status_code == 201

        token_trx: PaymentTransaction | None = PaymentTransaction.objects.last()
        assert token_trx
        assert token_trx.status == TransactionStatus.SUCCESS

    def test_withdraw_flow_no_user_data(
        self,
        wallet_cardpay_cards,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
        disable_error_logs,
    ):
        resp = cardpay_test_utils.make_deposit_request(merchant_client=merchant_client,
        )
        assert resp.status_code == 201

        trx = models.PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.SUCCESS
        assert trx.customer

        trx.customer.email = None
        trx.customer.save()

        trx.id_in_payment_system = None
        trx.save()

        # by card
        with patch.object(
            _BaseCardpayClient,
            "_get_withdraw_request",
            side_effect=SafeFlowInterruptionError("No email passed"),
        ):
            resp = cardpay_test_utils.make_withdraw_request(
                wallet=wallet_cardpay_cards,
                merchant_client=merchant_client,
                amount=30,
                user_data={
                    "phone": "123123123",
                    "email": "test@asd.com",
                },
            )
        assert resp.status_code == 201, resp.data

        card_trx: PaymentTransaction | None = PaymentTransaction.objects.last()
        assert card_trx

        assert card_trx.status == TransactionStatus.FAILED
        assert card_trx.decline_code == TransactionDeclineCodes.NO_OPERATION_PERFORMED
        assert card_trx.decline_reason == "No email passed"

    def test_client_refund_callback(
        self,
        wallet_cardpay_cards,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
    ):
        cardpay_test_utils.make_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_cards,
        )
        trx = PaymentTransaction.objects.get()

        assert trx.wallet.balance == 100

        with patch.object(
            CardpayController, "_is_callback_signature_valid", return_value=True
        ):
            resp = merchant_client.post(
                "/api/ps/cardpay-cards/",
                data={
                    "merchant_order": {
                        "id": str(trx.uuid),
                    },
                    "refund_data": {
                        "id": "1332155165",
                        "amount": "90",
                        "currency": "USD",
                        "status": "COMPLETED",
                    },
                },
                format="json",
            )
        assert resp.status_code == 200

        ic: IncomingCallback = IncomingCallback.objects.get()
        assert ic.status == CallbackStatus.SUCCESS

    @pytest.mark.parametrize("allow_negative_balances", [True, False])
    def test_withdraw_flow_success_with_negative_balance(
        self,
        wallet_cardpay_cards,
        merchant_client,
        mock_on_commit,
        mock_send_callback,
        allow_negative_balances,
    ):
        wallet_cardpay_cards.allow_negative_balances = allow_negative_balances
        wallet_cardpay_cards.save()

        resp = cardpay_test_utils.make_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_cards,
            amount=10,
        )
        assert resp.status_code == 201

        trx = models.PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.SUCCESS

        trx.id_in_payment_system = None
        trx.save()

        # by card
        resp = cardpay_test_utils.make_withdraw_request(
            wallet=wallet_cardpay_cards,
            merchant_client=merchant_client,
            amount=100,
        )

        if not allow_negative_balances:
            assert resp.status_code == 400
            assert resp.data == {
                "amount": [ErrorDetail(string="Insufficient funds.", code="invalid")]
            }
            return

        assert resp.status_code == 201

        card_trx: PaymentTransaction | None = PaymentTransaction.objects.last()
        assert card_trx

        assert card_trx.status == TransactionStatus.SUCCESS
        card_trx.id_in_payment_system = None
        card_trx.save()

        card_trx.wallet.refresh_from_db()
        assert card_trx.wallet.balance == Decimal("-90.00")

    def test_customer_deposits_with_appex_than_cardpay(
        self,
        wallet_appex,
        wallet_cardpay_cards,
        merchant_client,
    ):
        customer1 = "customer1"
        customer2 = "customer2"

        # Initiate appex request, customer1 and card created
        resp = appex_initiate_deposit(
            wallet_appex=wallet_appex,
            merchant_client=merchant_client,
            customer_external_id=customer1,
        )
        assert resp.status_code == 201
        cd: CustomerCard = CustomerCard.objects.last()  # type: ignore[assignment]
        assert cd.card_data_entity.to_dict() == {
            "card_cvv": "123",
            "card_expiration": "12/2026",
            "card_holder": "Card Holder",
            "card_num": "4111111111111111",
        }

        # Initiate cardpay deposit
        resp = cardpay_test_utils.make_deposit_request(
            merchant_client=merchant_client,
            wallet=wallet_cardpay_cards,
            customer_external_id=customer2,
        )
        assert resp.status_code == 201
        assert CustomerCard.objects.count() == 2
        cd: CustomerCard = CustomerCard.objects.last()  # type: ignore[no-redef]
        assert cd.card_data_entity.to_dict() == {
            "card_cvv": "123",
            "card_expiration": "12/2026",
            "card_holder": "Card Holder",
            "card_num": "4111111111111111",
        }

        trx: PaymentTransaction = PaymentTransaction.objects.last()  # type: ignore[assignment]
        trx.id_in_payment_system = None
        trx.save()

        # Initiate payout for customer 2
        withdrawal_resp = cardpay_test_utils.make_withdraw_request(
            wallet=wallet_cardpay_cards,
            merchant_client=merchant_client,
            card_token=resp.data["card_token"],
            customer_external_id=customer2,
        )
        assert withdrawal_resp.status_code == 201
        trx: PaymentTransaction = PaymentTransaction.objects.last()  # type: ignore[no-redef]
        assert trx.customer and trx.customer_card
        assert trx.customer.external_id == customer2
        assert trx.customer_card.customer.external_id == customer2
