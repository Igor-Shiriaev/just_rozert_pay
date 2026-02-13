import json
from datetime import timedelta

import pytest
import requests_mock
from django.utils import timezone
from django.utils.http import urlencode
from rozert_pay.common.const import (
    TransactionExtraFields,
    TransactionStatus,
    TransactionType,
)
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction, Wallet
from rozert_pay.payment.systems.nuvei import nuvei_const
from rozert_pay.payment.systems.nuvei.nuvei_controller import (
    NuveiController,
    nuvei_controller,
)
from rozert_pay.payment.tasks import check_status
from tests.factories import PaymentTransactionFactory

CARD = {
    "card_num": "4111111111111111",
    "card_expiration": "12/30",
    "card_holder": "IVAN IVANOV",
    "card_cvv": "123",
}

USER_DATA = {
    "email": "user@example.com",
    "country": "US",
    "ip_address": "127.0.0.1",
}


@pytest.mark.django_db
class TestNuveiSystem:
    def test_session_token_expired_status_returns_pending(
        self,
        wallet_nuvei: Wallet,
        currency_wallet_nuvei,
    ):
        trx = PaymentTransactionFactory.create(
            wallet=currency_wallet_nuvei,
            system_type=wallet_nuvei.system.type,
            status=TransactionStatus.PENDING,
            type=TransactionType.DEPOSIT,
            currency="USD",
            extra={
                nuvei_const.TRX_EXTRA_FIELD_SESSION_TOKEN: "session_123",
            },
        )

        with requests_mock.Mocker() as m:
            m.post(
                url="http://nuvei/getPaymentStatus.do",
                json={
                    "status": "ERROR",
                    "errCode": "1069",
                    "reason": "Session expired",
                },
            )
            remote_status = nuvei_controller.get_client(trx).get_transaction_status()

        assert isinstance(remote_status, RemoteTransactionStatus)
        assert remote_status.operation_status == TransactionStatus.PENDING
        assert (
            remote_status.raw_data["actualization_note"] == "Session token is expired"
        )

    def test_get_payment_status_1140_returns_pending_for_recent_trx(
        self,
        wallet_nuvei: Wallet,
        currency_wallet_nuvei,
    ):
        trx = PaymentTransactionFactory.create(
            wallet=currency_wallet_nuvei,
            system_type=wallet_nuvei.system.type,
            status=TransactionStatus.PENDING,
            type=TransactionType.DEPOSIT,
            currency="USD",
            extra={
                nuvei_const.TRX_EXTRA_FIELD_SESSION_TOKEN: "session_123",
            },
        )
        PaymentTransaction.objects.filter(id=trx.id).update(
            created_at=timezone.now() - timedelta(minutes=10),
        )
        trx.refresh_from_db()

        with requests_mock.Mocker() as m:
            m.post(
                url="http://nuvei/getPaymentStatus.do",
                json={
                    "reason": "A payment was not performed during this session",
                    "status": "ERROR",
                    "errCode": 1140,
                    "version": "1.0",
                    "sessionToken": "65c99bcc8b844b8d94d511079e8717030121",
                    "internalRequestId": 1770375652944,
                },
            )
            remote_status = nuvei_controller.get_client(trx).get_transaction_status()

        assert isinstance(remote_status, RemoteTransactionStatus)
        assert remote_status.operation_status == TransactionStatus.PENDING

    def test_get_payment_status_1140_returns_failed_for_old_trx(
        self,
        wallet_nuvei: Wallet,
        currency_wallet_nuvei,
    ):
        trx = PaymentTransactionFactory.create(
            wallet=currency_wallet_nuvei,
            system_type=wallet_nuvei.system.type,
            status=TransactionStatus.PENDING,
            type=TransactionType.DEPOSIT,
            currency="USD",
            extra={
                nuvei_const.TRX_EXTRA_FIELD_SESSION_TOKEN: "session_123",
            },
        )
        PaymentTransaction.objects.filter(id=trx.id).update(
            created_at=timezone.now() - timedelta(minutes=20),
        )
        trx.refresh_from_db()

        with requests_mock.Mocker() as m:
            m.post(
                url="http://nuvei/getPaymentStatus.do",
                json={
                    "reason": "A payment was not performed during this session",
                    "status": "ERROR",
                    "errCode": 1140,
                    "version": "1.0",
                    "sessionToken": "65c99bcc8b844b8d94d511079e8717030121",
                    "internalRequestId": 1770375652944,
                },
            )
            remote_status = nuvei_controller.get_client(trx).get_transaction_status()

        assert isinstance(remote_status, RemoteTransactionStatus)
        assert remote_status.operation_status == TransactionStatus.FAILED

    def test_deposit_success_callback_approved(
        self,
        merchant_client,
        wallet_nuvei: Wallet,
        mock_on_commit,
        mock_send_callback,
        mock_check_status_task,
        monkeypatch,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="http://nuvei/getSessionToken",
                json={
                    "status": "SUCCESS",
                    "sessionToken": "session_123",
                },
            )
            m.post(
                url="http://nuvei/initPayment.do",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "APPROVED",
                    "transactionId": "trx_123",
                    "paymentOption": {"card": {"threeD": {"v2supported": "false"}}},
                },
            )
            m.post(
                url="http://nuvei/payment",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "APPROVED",
                    "transactionId": "trx_123",
                },
            )
            monkeypatch.setattr(
                NuveiController,
                "_is_callback_signature_valid",
                lambda *a, **k: True,
            )

            response = merchant_client.post(
                path="/api/payment/v1/nuvei/deposit/",
                data={
                    "amount": "100.00",
                    "currency": "USD",
                    "wallet_id": str(wallet_nuvei.uuid),
                    "customer_id": "customer-1",
                    "card": CARD,
                    "user_data": USER_DATA,
                },
                format="json",
            )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING

            callback_payload = {
                "Status": "APPROVED",
                "clientUniqueId": str(trx.uuid),
                "totalAmount": "100.00",
                "currency": "USD",
                "PPP_TransactionID": "trx_123",
            }
            callback_resp = merchant_client.post(
                path="/api/payment/v1/callback/nuvei/",
                data=urlencode(callback_payload),
                content_type="application/x-www-form-urlencoded",
            )
            assert callback_resp.status_code == 200

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

    def test_deposit_decline_callback(
        self,
        merchant_client,
        wallet_nuvei: Wallet,
        mock_on_commit,
        mock_send_callback,
        mock_check_status_task,
        monkeypatch,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="http://nuvei/getSessionToken",
                json={
                    "status": "SUCCESS",
                    "sessionToken": "session_123",
                },
            )
            m.post(
                url="http://nuvei/initPayment.do",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "APPROVED",
                    "transactionId": "trx_123",
                    "paymentOption": {"card": {"threeD": {"v2supported": "false"}}},
                },
            )
            m.post(
                url="http://nuvei/payment",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "DECLINED",
                    "transactionId": "trx_123",
                    "gwErrorReason": "DECLINE_CODE",
                    "gwErrorCode": "Declined",
                },
            )
            monkeypatch.setattr(
                NuveiController,
                "_is_callback_signature_valid",
                lambda *a, **k: True,
            )

            response = merchant_client.post(
                path="/api/payment/v1/nuvei/deposit/",
                data={
                    "amount": "100.00",
                    "currency": "USD",
                    "wallet_id": str(wallet_nuvei.uuid),
                    "customer_id": "customer-1",
                    "card": CARD,
                    "user_data": USER_DATA,
                },
                format="json",
            )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING

            callback_payload = {
                "Status": "ERROR",
                "clientUniqueId": str(trx.uuid),
                "totalAmount": "100.00",
                "currency": "USD",
                "ReasonCode": "DECLINE_CODE",
                "Reason": "Declined",
                "PPP_TransactionID": "trx_123",
            }
            callback_resp = merchant_client.post(
                path="/api/payment/v1/callback/nuvei/",
                data=urlencode(callback_payload),
                content_type="application/x-www-form-urlencoded",
            )
            assert callback_resp.status_code == 200

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.FAILED
            assert trx.decline_code == "DECLINE_CODE"

    def test_redirect_success_flow(
        self,
        merchant_client,
        wallet_nuvei: Wallet,
        mock_on_commit,
        mock_send_callback,
        mock_check_status_task,
        monkeypatch,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="http://nuvei/getSessionToken",
                json={
                    "status": "SUCCESS",
                    "sessionToken": "session_123",
                },
            )
            m.post(
                url="http://nuvei/initPayment.do",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "APPROVED",
                    "transactionId": "init_123",
                    "paymentOption": {"card": {"threeD": {"v2supported": "true"}}},
                },
            )
            m.post(
                url="http://nuvei/payment",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "REDIRECT",
                    "transactionId": "trx_123",
                    "paymentOption": {
                        "card": {
                            "threeD": {
                                "acsUrl": "https://3ds",
                                "cReq": "creq",
                            }
                        }
                    },
                },
            )
            m.post(
                url="http://nuvei/getPaymentStatus.do",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "APPROVED",
                    "transactionId": "trx_123",
                    "amount": "100.00",
                    "currency": "USD",
                    "errCode": "0",
                    "reason": "Approved",
                },
            )
            monkeypatch.setattr(
                NuveiController,
                "_is_callback_signature_valid",
                lambda *a, **k: True,
            )

            response = merchant_client.post(
                path="/api/payment/v1/nuvei/deposit/",
                data={
                    "amount": "100.00",
                    "currency": "USD",
                    "wallet_id": str(wallet_nuvei.uuid),
                    "customer_id": "customer-1",
                    "card": CARD,
                    "user_data": USER_DATA,
                    "redirect_url": "https://merchant.example/return",
                },
                format="json",
            )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING
            assert trx.form

            redirect_resp = merchant_client.post(
                f"/api/payment/v1/redirect/nuvei/?transaction_id={trx.uuid}",
                data={"transStatus": "Y"},
            )
            assert redirect_resp.status_code == 302

            check_status(trx.id)
            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS
            assert trx.extra[TransactionExtraFields.REDIRECT_RECEIVED_DATA] == {
                "transStatus": "Y",
            }

    def test_redirect_failure_declines_immediately(
        self,
        merchant_client,
        wallet_nuvei: Wallet,
        mock_on_commit,
        mock_send_callback,
        mock_check_status_task,
        monkeypatch,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="http://nuvei/getSessionToken",
                json={
                    "status": "SUCCESS",
                    "sessionToken": "session_123",
                },
            )
            m.post(
                url="http://nuvei/initPayment.do",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "APPROVED",
                    "transactionId": "init_123",
                    "paymentOption": {"card": {"threeD": {"v2supported": "true"}}},
                },
            )
            m.post(
                url="http://nuvei/payment",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "REDIRECT",
                    "transactionId": "trx_123",
                    "paymentOption": {
                        "card": {
                            "threeD": {
                                "acsUrl": "https://3ds",
                                "cReq": "creq",
                            }
                        }
                    },
                },
            )
            monkeypatch.setattr(
                NuveiController,
                "_is_callback_signature_valid",
                lambda *a, **k: True,
            )

            response = merchant_client.post(
                path="/api/payment/v1/nuvei/deposit/",
                data={
                    "amount": "100.00",
                    "currency": "USD",
                    "wallet_id": str(wallet_nuvei.uuid),
                    "customer_id": "customer-1",
                    "card": CARD,
                    "user_data": USER_DATA,
                    "redirect_url": "https://merchant.example/return",
                },
                format="json",
            )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING

            redirect_resp = merchant_client.post(
                f"/api/payment/v1/redirect/nuvei/?transaction_id={trx.uuid}",
                data={
                    "transStatus": "N",
                    "errorCode": "ERR",
                    "errorDescription": "desc",
                },
            )
            assert redirect_resp.status_code == 302

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.FAILED
            assert trx.decline_code == "ERR"

    def test_redirect_final_sale_with_new_transaction_id_becomes_success(
        self,
        merchant_client,
        wallet_nuvei: Wallet,
        mock_on_commit,
        mock_send_callback,
        mock_check_status_task,
        monkeypatch,
    ):
        init_transaction_id = "1120000006020682251"
        redirect_transaction_id = "1120000006020682545"
        final_sale_transaction_id = "1120000006020685624"
        session_token = "session_masked_44823"

        with requests_mock.Mocker() as m:
            m.post(
                url="http://nuvei/getSessionToken",
                json={
                    "status": "SUCCESS",
                    "sessionToken": session_token,
                },
            )
            m.post(
                url="http://nuvei/initPayment.do",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "APPROVED",
                    "transactionType": "InitAuth3D",
                    "transactionId": init_transaction_id,
                    "paymentOption": {"card": {"threeD": {"v2supported": "true"}}},
                },
            )
            m.post(
                "http://nuvei/payment",
                [
                    {
                        "json": {
                            "status": "SUCCESS",
                            "transactionStatus": "REDIRECT",
                            "transactionType": "Auth3D",
                            "transactionId": redirect_transaction_id,
                            "paymentOption": {
                                "card": {
                                    "threeD": {
                                        "acsUrl": "https://acs.example/challenge",
                                        "cReq": "creq_masked",
                                    }
                                }
                            },
                        }
                    },
                    {
                        "json": {
                            "status": "SUCCESS",
                            "transactionStatus": "APPROVED",
                            "transactionType": "Sale",
                            "transactionId": final_sale_transaction_id,
                        }
                    },
                ],
            )
            m.post(
                url="http://nuvei/getPaymentStatus.do",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "APPROVED",
                    "transactionType": "Sale",
                    "transactionId": final_sale_transaction_id,
                    "amount": "100.00",
                    "currency": "USD",
                    "errCode": "0",
                    "reason": "",
                },
            )
            monkeypatch.setattr(
                NuveiController,
                "_is_callback_signature_valid",
                lambda *a, **k: True,
            )

            response = merchant_client.post(
                path="/api/payment/v1/nuvei/deposit/",
                data={
                    "amount": "100.00",
                    "currency": "USD",
                    "wallet_id": str(wallet_nuvei.uuid),
                    "customer_id": "customer-masked",
                    "card": CARD,
                    "user_data": USER_DATA,
                    "redirect_url": "https://merchant.example/return",
                },
                format="json",
            )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING
            assert trx.id_in_payment_system == redirect_transaction_id

            redirect_resp = merchant_client.post(
                f"/api/payment/v1/redirect/nuvei/?transaction_id={trx.uuid}",
                data={"transStatus": "Y"},
            )
            assert redirect_resp.status_code == 302

            check_status(trx.id)
            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS
            assert trx.id_in_payment_system == final_sale_transaction_id
            assert trx.extra[nuvei_const.TRX_EXTRA_FIELD_THREEDS_TRANSACTION_IDS] == [
                redirect_transaction_id,
                final_sale_transaction_id,
            ]

    def test_withdraw_success_callback_response(
        self,
        merchant_client,
        wallet_nuvei: Wallet,
        currency_wallet_nuvei,
        mock_on_commit,
        mock_send_callback,
        mock_check_status_task,
        monkeypatch,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                url="http://nuvei/payout.do",
                json={
                    "status": "SUCCESS",
                    "transactionStatus": "APPROVED",
                    "transactionId": "payout_123",
                },
            )
            monkeypatch.setattr(
                NuveiController,
                "_is_callback_signature_valid",
                lambda *a, **k: True,
            )

            response = merchant_client.post(
                path="/api/payment/v1/nuvei/withdraw/card-data/",
                data={
                    "amount": "50.00",
                    "currency": "USD",
                    "wallet_id": str(wallet_nuvei.uuid),
                    "customer_id": "customer-1",
                    "card": {
                        "card_num": CARD["card_num"],
                        "card_expiration": CARD["card_expiration"],
                        "card_holder": CARD["card_holder"],
                    },
                    "user_data": USER_DATA,
                },
                format="json",
            )
            assert response.status_code == 201

            trx = PaymentTransaction.objects.get()
            assert trx.status == TransactionStatus.PENDING
            assert trx.id_in_payment_system == "payout_123"

            callback_payload = {
                "wdRequestStatus": "Pending",
                "wdRequestState": "Open",
                "clientUniqueId": str(trx.uuid),
                "wd_amount": "50.00",
                "wd_currency": "USD",
                "transactionId": "payout_123",
            }
            callback_resp = merchant_client.post(
                path="/api/payment/v1/callback/nuvei/",
                data=urlencode(callback_payload),
                content_type="application/x-www-form-urlencoded",
            )
            assert callback_resp.status_code == 200
            assert b"action=Approve" in callback_resp.content

    def test_chargeback_callback_marks_transaction(
        self,
        merchant_client,
        wallet_nuvei: Wallet,
        currency_wallet_nuvei,
        mock_on_commit,
        mock_send_callback,
        mock_check_status_task,
        monkeypatch,
    ):
        trx: PaymentTransaction = PaymentTransactionFactory.create(
            wallet=currency_wallet_nuvei,
            system_type=wallet_nuvei.system.type,
            status=TransactionStatus.SUCCESS,
            type=TransactionType.DEPOSIT,
        )
        trx.id_in_payment_system = "trx_123"
        trx.save(update_fields=["id_in_payment_system", "updated_at"])
        monkeypatch.setattr(
            NuveiController,
            "_is_callback_signature_valid",
            lambda *a, **k: True,
        )
        callback_payload = {
            "EventType": "Chargeback",
            "Chargeback": {
                "Type": "Chargeback",
                "ReportedAmount": "100.00",
                "ReportedCurrency": "USD",
            },
            "TransactionDetails": {
                "ClientUniqueId": str(trx.uuid),
            },
            "TransactionID": "trx_123",
        }
        callback_resp = merchant_client.post(
            path="/api/payment/v1/callback/nuvei/",
            data=json.dumps(callback_payload),
            content_type="application/json",
        )
        assert callback_resp.status_code == 200

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.CHARGED_BACK
        assert trx.extra[TransactionExtraFields.IS_CHARGEBACK_RECEIVED]

    def test_callback_after_failed_transaction_keeps_status(
        self,
        merchant_client,
        wallet_nuvei: Wallet,
        currency_wallet_nuvei,
        mock_on_commit,
        mock_send_callback,
        monkeypatch,
    ):
        trx: PaymentTransaction = PaymentTransactionFactory.create(
            wallet=currency_wallet_nuvei,
            system_type=wallet_nuvei.system.type,
            status=TransactionStatus.FAILED,
            type=TransactionType.DEPOSIT,
            decline_code="EXEC_TOO_LONG",
            decline_reason="callback not received in time",
        )

        monkeypatch.setattr(
            NuveiController,
            "_is_callback_signature_valid",
            lambda *a, **k: True,
        )
        callback_payload = {
            "Status": "ERROR",
            "clientUniqueId": str(trx.uuid),
            "totalAmount": "100.00",
            "currency": "USD",
            "ReasonCode": "EXEC_TOO_LONG",
            "Reason": "callback not received in time",
            "PPP_TransactionID": "trx_123",
        }
        callback_resp = merchant_client.post(
            path="/api/payment/v1/callback/nuvei/",
            data=urlencode(callback_payload),
            content_type="application/x-www-form-urlencoded",
        )
        assert callback_resp.status_code == 200

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "EXEC_TOO_LONG"
        assert trx.decline_reason == "callback not received in time"

        cb = IncomingCallback.objects.get()
        assert cb.status == "success"
