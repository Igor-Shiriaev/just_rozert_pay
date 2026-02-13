from unittest import mock

from rozert_pay.common import const
from rozert_pay.common.const import TransactionType
from rozert_pay.payment.models import (
    IncomingCallback,
    OutcomingCallback,
    PaymentTransaction,
)
from tests.conftest import requests_mocker
from tests.payment.api_v1.test_views import force_authenticate


class TestPayCash:
    def test_deposit_success(
        self,
        api_client,
        merchant,
        wallet_paycash,
        django_capture_on_commit_callbacks,
    ):
        force_authenticate(api_client, merchant)

        with requests_mocker() as m:
            m.post(
                "http://fake.com/v1/reference",
                json={
                    "Reference": "1522289200026",
                },
            )
            m.get(
                "http://fake.com/v1/authre?key=fake",
                json={
                    "Authorization": "fake",
                    "ExpiresIn": "6/30/2071 2:36:51 PM",
                },
            )
            m.get(
                "http://fake.com/v1/payments?Date=2024-12-02",
                json=TRANSACTION_STATUS_RESPONSE_SUCCESS,
            )

            response = api_client.post(
                "/api/payment/v1/transaction/",
                {
                    "type": TransactionType.DEPOSIT,
                    "amount": "100.00",
                    "currency": "MXN",
                    "wallet_id": wallet_paycash.uuid,
                    "customer_id": "customer1",
                },
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            instruction = {
                "link": LINK_URL,
                "type": "instruction_file",
            }
            assert trx.instruction == instruction
            assert trx.id_in_payment_system == "1522289200026"
            assert trx.customer
            assert response.json() == {
                "amount": "100.00",
                "callback_url": mock.ANY,
                "created_at": mock.ANY,
                "currency": "MXN",
                "customer_id": str(trx.customer.uuid),
                "decline_code": None,
                "form": None,
                "user_data": mock.ANY,
                "decline_reason": None,
                "card_token": None,
                "external_account_id": None,
                "id": str(trx.uuid),
                "instruction": None,
                "status": "pending",
                "type": "deposit",
                "external_customer_id": str(trx.customer.external_id),
                "updated_at": mock.ANY,
                "wallet_id": str(trx.wallet.wallet.uuid),
            }

            # Fetch instruction
            response = api_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json()["instruction"] == instruction

            assert OutcomingCallback.objects.count() == 1
            cb = OutcomingCallback.objects.get()

            assert cb.body["instruction"] == {
                "link": LINK_URL,
                "type": "instruction_file",
            }

            # Receive callback
            with django_capture_on_commit_callbacks(execute=False) as callbacks:
                response = api_client.post(
                    "/api/payment/v1/callback/paycash/",
                    data=CALLBACK_SUCCESS,
                    format="json",
                )
                assert response.status_code == 200
                assert response.json() == {
                    "code": 200,
                    "message": "payment successfully notified",
                }
                assert IncomingCallback.objects.count() == 1

            assert len(callbacks) == 1

            trx.refresh_from_db()
            assert trx.status == const.TransactionStatus.PENDING

            with django_capture_on_commit_callbacks(execute=True):
                callbacks[0]()

            trx.refresh_from_db()
            assert trx.status == const.TransactionStatus.SUCCESS
            assert OutcomingCallback.objects.count() == 2
            last: OutcomingCallback | None = OutcomingCallback.objects.order_by(
                "created_at"
            ).last()
            assert last and last.body == {
                "amount": "100.00",
                "created_at": mock.ANY,
                "currency": "MXN",
                "customer_id": str(trx.customer.uuid),
                "decline_code": None,
                "decline_reason": None,
                "card_token": None,
                "external_account_id": None,
                "form": None,
                "user_data": mock.ANY,
                "id": mock.ANY,
                "instruction": {
                    "link": LINK_URL,
                    "type": "instruction_file",
                },
                "status": "success",
                "type": "deposit",
                "updated_at": mock.ANY,
                "wallet_id": mock.ANY,
                "external_customer_id": "customer1",
                "callback_url": mock.ANY,
            }

    def test_sandbox_deposit_success(
        self, api_client, merchant, wallet_paycash, mock_on_commit
    ):
        merchant.sandbox = True
        merchant.save()

        force_authenticate(api_client, merchant)

        with requests_mocker():
            response = api_client.post(
                "/api/payment/v1/transaction/",
                {
                    "type": TransactionType.DEPOSIT,
                    "amount": "100.00",
                    "currency": "MXN",
                    "wallet_id": wallet_paycash.uuid,
                    "customer_id": "customer1",
                },
            )

        assert response.status_code == 201
        trx = PaymentTransaction.objects.get()
        assert trx.instruction == {
            "link": mock.ANY,
            "type": "instruction_file",
        }
        assert trx.instruction["link"].startswith(
            "http://ec2-3-140-103-165.us-east-2.compute.amazonaws.com:8085/formato.php?emisor=QzA1M0VDRjlFRDQxREYwMzExQjlERjEzQ0M2QzNCNjA3OEQyRDNDMg==&token=QzA1M0VDRjlFRDQxREYwMzExQjlERjEzQ0M2QzNCNjA3OEQyRDNDMg==&referencia="
        )

        assert trx.status == const.TransactionStatus.SUCCESS
        assert OutcomingCallback.objects.count() == 2
        assert trx.id_in_payment_system
        assert trx.id_in_payment_system.startswith("sandbox:paycash:")
        cb = OutcomingCallback.objects.order_by("created_at").last()
        assert cb and trx.customer
        assert cb.body == {
            "amount": "100.00",
            "created_at": mock.ANY,
            "currency": "MXN",
            "customer_id": str(trx.customer.uuid),
            "decline_code": None,
            "decline_reason": None,
            "card_token": None,
            "external_account_id": None,
            "external_customer_id": str(trx.customer.external_id),
            "form": None,
            "user_data": mock.ANY,
            "id": str(trx.uuid),
            "instruction": {
                "link": mock.ANY,
                "type": "instruction_file",
            },
            "status": "success",
            "type": "deposit",
            "updated_at": mock.ANY,
            "wallet_id": str(trx.wallet.wallet.uuid),
            "callback_url": mock.ANY,
        }

    def test_deposit_failure_invalid_amount(
        self, api_client, merchant, wallet_paycash, mock_on_commit
    ):
        force_authenticate(api_client, merchant)

        with requests_mocker() as m:
            m.post(
                "http://fake.com/v1/reference",
                json={
                    "ErrorCode": "25",
                    "ErrorMessage": "Monto invalido, monto superior al maximo configurado.",
                },
                status_code=200,
            )
            m.get(
                "http://fake.com/v1/authre?key=fake",
                json={
                    "Authorization": "fake",
                    "ExpiresIn": "6/30/2071 2:36:51 PM",
                },
            )

            response = api_client.post(
                "/api/payment/v1/transaction/",
                {
                    "type": TransactionType.DEPOSIT,
                    "amount": "14000.00",
                    "currency": "MXN",
                    "wallet_id": wallet_paycash.uuid,
                    "customer_id": "customer1",
                },
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            assert trx.status == const.TransactionStatus.FAILED
            assert trx.decline_code == "25"
            assert (
                trx.decline_reason
                == "Monto invalido, monto superior al maximo configurado."
            )

            assert trx.instruction is None

            assert OutcomingCallback.objects.count() == 1
            cb = OutcomingCallback.objects.get()
            assert cb.body["status"] == "failed"
            assert cb.body["decline_code"] == "25"
            assert (
                cb.body["decline_reason"]
                == "Monto invalido, monto superior al maximo configurado."
            )
            assert cb.body["instruction"] is None


CALLBACK_SUCCESS = {
    "payment": {
        "Folio": 17902592,
        "Resultado": 0,
        "Tipo": 1,
        "Emisor": 522,
        "Secuencia": 13,
        "Monto": 10.00,
        "Fecha": "02/12/2024",
        "Hora": "10:39:27",
        "Autorizacion": "1733156839",
        "Referencia": "1522289200026",
        "Value": "202b7a8a-118f-459a-b780-8c868b84c49d",
        "FechaCreacion": "2024-12-02T10:53:40.4453702-06:00",
        "FechaConfirmation": "2024-12-02T10:53:40.4453702-06:00",
        "FechaVencimiento": "2024-12-02T10:53:40.4453702-06:00",
    }
}

CALLBACK_ERROR = {"code": 200, "message": "payment successfully notified"}


TRANSACTION_STATUS_RESPONSE_SUCCESS = [
    {
        "ErrorCode": "0",
        "ErrorMessage": "Operacion Exitosa.",
        "Payments": [
            {
                "Amount": 100,
                "Authorization": "1733156839",
                "Commission": 0,
                "Date": "2024-12-2",
                "Hour": "10:39:27",
                "PaymentId": 17902592,
                "RefValue": "202b7a8a-118f-459a-b780-8c868b84c49d",
                "Reference": "1522289200026",
                "SenderId": 522,
                "Sequence": 13,
                "Status": "0",
                "Type": 1,
            }
        ],
    }
]

LINK_URL = "http://ec2-3-140-103-165.us-east-2.compute.amazonaws.com:8085/formato.php?emisor=QzA1M0VDRjlFRDQxREYwMzExQjlERjEzQ0M2QzNCNjA3OEQyRDNDMg==&token=QzA1M0VDRjlFRDQxREYwMzExQjlERjEzQ0M2QzNCNjA3OEQyRDNDMg==&referencia=MTUyMjI4OTIwMDAyNg=="
