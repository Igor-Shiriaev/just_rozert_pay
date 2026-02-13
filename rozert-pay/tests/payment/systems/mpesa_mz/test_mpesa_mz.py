from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

from requests import Response
from rest_framework.test import APIClient
from rozert_pay.common import const
from rozert_pay.common.const import CallbackStatus, TransactionStatus
from rozert_pay.payment.models import (
    CustomerExternalPaymentSystemAccount,
    IncomingCallback,
    Merchant,
    PaymentTransaction,
    Wallet,
)
from tests.payment.api_v1 import matchers
from tests.payment.systems.mpesa_mz.constants import (
    AMOUNT,
    CURRENCY,
    MPESA_MZ_DEPOSIT_CALLBACK,
    MPESA_MZ_WITHDRAWAL_CALLBACK,
    PHONE_NUMBER,
)


def _sdk_response(*, success: bool, code: str, description: str, data=None):
    return SimpleNamespace(
        success=success,
        status=SimpleNamespace(code=code, description=description),
        data=data or {},
    )


def _create_deposit(
    merchant_client: APIClient,
    wallet: Wallet,
    *,
    amount: int | str | Decimal = AMOUNT,
    currency: str = CURRENCY,
    customer_id: str = "customer1",
    phone: str = PHONE_NUMBER,
    mocker=None,
    receive=None,
    send=None,
    query=None,
    patch_event_log: bool = False,
) -> tuple[Response, PaymentTransaction]:
    if mocker is not None:
        if patch_event_log:
            mocker.patch(
                "rozert_pay.payment.systems.mpesa_mz.client.event_logs.create_transaction_log"
            )
        mpesa_sdk_client = mocker.patch(
            "rozert_pay.payment.systems.mpesa_mz.client.MpesaSdkClient"
        )
        client_instance = mpesa_sdk_client.return_value

        def _set_mock(method, value):
            if value is None:
                return
            if callable(value):
                method.side_effect = value
            else:
                method.return_value = value

        _set_mock(client_instance.receive, receive)
        _set_mock(client_instance.send, send)
        _set_mock(client_instance.query, query)

    response = merchant_client.post(
        path="/api/payment/v1/mpesa-mz/deposit/",
        data={
            "amount": amount,
            "currency": currency,
            "wallet_id": wallet.uuid,
            "customer_id": customer_id,
            "user_data": {
                "phone": phone,
            },
        },
        format="json",
    )
    trx = (
        PaymentTransaction.objects.filter(type=const.TransactionType.DEPOSIT)
        .order_by("-id")
        .first()
    )
    assert trx
    return response, trx  # type: ignore[return-value]


class TestMpesaMzSystem:
    def test_deposit_success(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_mpesa_mz: Wallet,
        mock_send_callback,
        mock_check_status_task,
        mocker,
    ):
        mock_event_log = mocker.patch(
            "rozert_pay.payment.systems.mpesa_mz.client.event_logs.create_transaction_log"
        )
        response, trx = _create_deposit(
            merchant_client,
            wallet_mpesa_mz,
            mocker=mocker,
            receive=lambda payload: _sdk_response(
                success=True,
                code="INS-0",
                description="Request processed successfully",
                data={"reference": payload["reference"]},
            ),
            query=lambda payload: _sdk_response(
                success=True,
                code="INS-0",
                description="Request processed successfully",
                data={
                    "output_ResponseTransactionStatus": "Success",
                    "reference": payload["reference"],
                },
            ),
        )
        assert response.status_code == 201

        assert trx is not None

        assert trx.id_in_payment_system == str(trx.uuid).split("-")[0]
        assert trx.check_status_until
        assert trx.status == TransactionStatus.PENDING
        assert mock_event_log.call_count >= 1

        # Customer external account is created on transaction creation
        account = CustomerExternalPaymentSystemAccount.objects.filter(
            customer=trx.customer,
            wallet=trx.wallet.wallet,
            system_type=const.PaymentSystemType.MPESA_MZ,
            unique_account_number=PHONE_NUMBER,
        ).first()
        assert account is not None
        assert account.active

        # Callback
        callback_data = deepcopy(MPESA_MZ_DEPOSIT_CALLBACK)
        callback_data["output_ThirdPartyReference"] = str(trx.uuid)
        response = merchant_client.post(  # type: ignore[assignment]
            path="/api/payment/v1/callback/mpesa-mz/",
            data=callback_data,
            format="json",
        )
        assert response.status_code == 200

        incoming_callback = IncomingCallback.objects.get()
        assert (
            incoming_callback.status == CallbackStatus.SUCCESS
        ), incoming_callback.error

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS

        assert trx.customer_external_account
        assert trx.customer_external_account.unique_account_number == "258841234567"

        # Transaction status
        response = merchant_client.get(  # type: ignore[assignment]
            path=f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200
        parsed = response.json()
        assert parsed == matchers.DictContains(
            {
                "amount": AMOUNT,
                "currency": CURRENCY,
                "status": "success",
                "type": "deposit",
                "user_data": matchers.DictContains(
                    {
                        "phone": PHONE_NUMBER,
                    }
                ),
            }
        )
        assert parsed["external_account_id"] == "258841234567"

    def test_deposit_failed_instantly(
        self,
        merchant_client: APIClient,
        merchant: Merchant,
        wallet_mpesa_mz: Wallet,
        mock_check_status_task,
        mocker,
    ):
        mock_event_log = mocker.patch(
            "rozert_pay.payment.systems.mpesa_mz.client.event_logs.create_transaction_log"
        )
        response, trx = _create_deposit(
            merchant_client,
            wallet_mpesa_mz,
            mocker=mocker,
            receive=_sdk_response(
                success=True,
                code="INS-1",
                description="Invalid request",
                data={},
            ),
        )
        assert response.status_code == 201
        assert trx is not None

        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "INS-1"
        assert mock_event_log.call_count >= 1

    def test_withdraw_success(
        self,
        merchant_client: APIClient,
        wallet_mpesa_mz: Wallet,
        currency_wallet_mpesa_mz,
        mock_check_status_task,
        mocker,
    ):
        # First create a deposit to link phone number
        deposit_response, deposit_trx = _create_deposit(
            merchant_client,
            wallet_mpesa_mz,
            mocker=mocker,
            receive=lambda payload: _sdk_response(
                success=True,
                code="INS-0",
                description="Request processed successfully",
                data={"reference": payload["reference"]},
            ),
            send=lambda payload: _sdk_response(
                success=True,
                code="INS-0",
                description="Request processed successfully",
                data={"reference": payload["reference"]},
            ),
            query=lambda payload: _sdk_response(
                success=True,
                code="INS-0",
                description="Request processed successfully",
                data={
                    "output_ResponseTransactionStatus": "Success",
                    "reference": payload["reference"],
                },
            ),
        )
        assert deposit_response.status_code == 201
        assert deposit_trx is not None
        assert deposit_trx.customer_external_account is not None

        # Now test withdrawal
        response = merchant_client.post(
            path="/api/payment/v1/mpesa-mz/withdraw/",
            data={
                "amount": AMOUNT,
                "currency": CURRENCY,
                "wallet_id": wallet_mpesa_mz.uuid,
                "customer_id": "customer1",
                "withdraw_to_account": deposit_trx.customer_external_account.unique_account_number,
            },
            format="json",
        )
        assert response.status_code == 201
        trx = PaymentTransaction.objects.filter(
            type=const.TransactionType.WITHDRAWAL
        ).first()
        assert trx is not None

        assert trx.check_status_until
        assert trx.status == TransactionStatus.PENDING
        assert trx.customer_external_account is not None
        assert trx.customer_external_account.unique_account_number == PHONE_NUMBER

        # Callback
        callback_data = deepcopy(MPESA_MZ_WITHDRAWAL_CALLBACK)
        callback_data["output_ThirdPartyReference"] = str(trx.uuid)
        response = merchant_client.post(
            path="/api/payment/v1/callback/mpesa-mz/",
            data=callback_data,
            format="json",
        )
        assert response.status_code == 200

        cb = IncomingCallback.objects.filter(
            transaction__type=const.TransactionType.WITHDRAWAL
        ).first()
        assert cb is not None
        assert cb.status == CallbackStatus.SUCCESS, cb.error

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS

        # Transaction status
        response = merchant_client.get(
            path=f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200
        assert response.json() == matchers.DictContains(
            {
                "amount": AMOUNT,
                "currency": CURRENCY,
                "status": "success",
                "type": "withdrawal",
            }
        )

    def test_withdraw_failed_instantly(
        self,
        merchant_client: APIClient,
        wallet_mpesa_mz: Wallet,
        currency_wallet_mpesa_mz,
        mocker,
    ):
        # First create a deposit to link phone number
        mock_event_log = mocker.patch(
            "rozert_pay.payment.systems.mpesa_mz.client.event_logs.create_transaction_log"
        )
        deposit_response, deposit_trx = _create_deposit(
            merchant_client,
            wallet_mpesa_mz,
            mocker=mocker,
            receive=lambda payload: _sdk_response(
                success=True,
                code="INS-0",
                description="Request processed successfully",
                data={"reference": payload["reference"]},
            ),
            send=_sdk_response(
                success=True,
                code="INS-1",
                description="Invalid request",
                data={},
            ),
            query=lambda payload: _sdk_response(
                success=True,
                code="INS-0",
                description="Request processed successfully",
                data={
                    "output_ResponseTransactionStatus": "Success",
                    "reference": payload["reference"],
                },
            ),
        )
        assert deposit_response.status_code == 201
        assert deposit_trx is not None
        assert isinstance(deposit_trx, PaymentTransaction)

        # Simulate successful deposit callback
        callback_data = deepcopy(MPESA_MZ_DEPOSIT_CALLBACK)
        callback_data["output_ThirdPartyReference"] = str(deposit_trx.uuid)
        merchant_client.post(
            path="/api/payment/v1/callback/mpesa-mz/",
            data=callback_data,
            format="json",
        )

        # Now test failed withdrawal
        assert deposit_trx.customer_external_account

        response = merchant_client.post(
            path="/api/payment/v1/mpesa-mz/withdraw/",
            data={
                "amount": AMOUNT,
                "currency": CURRENCY,
                "wallet_id": wallet_mpesa_mz.uuid,
                "customer_id": "customer1",
                "withdraw_to_account": deposit_trx.customer_external_account.unique_account_number,
            },
            format="json",
        )
        assert response.status_code == 201
        trx = PaymentTransaction.objects.filter(
            type=const.TransactionType.WITHDRAWAL
        ).first()
        assert trx is not None

        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "INS-1"
        assert mock_event_log.call_count >= 2
