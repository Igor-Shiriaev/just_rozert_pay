import base64
import typing as ty
from io import BytesIO
from unittest import mock

import requests_mock
from PIL import Image
from rest_framework.response import Response
from rest_framework.test import APIClient
from rozert_pay.common.const import CallbackStatus, TransactionStatus
from rozert_pay.payment import tasks
from rozert_pay.payment.admin import PaymentTransactionAdmin
from rozert_pay.payment.models import (
    IncomingCallback,
    PaymentTransaction,
    PaymentTransactionEventLog,
    Wallet,
)
from rozert_pay.payment.systems.stp_codi.entities import StpCodiDepositType
from rozert_pay.payment.systems.stp_codi.models import StpCodiUniqueIds
from tests.factories import PaymentTransactionFactory, UserFactory
from tests.payment.api_v1 import matchers


def make_stp_codi_request(
    merchant_client: APIClient,
    wallet: Wallet,
    deposit_response: dict[str, ty.Any] | None = None,
) -> Response:
    with requests_mock.Mocker() as m:
        m.post(
            "https://sandbox-api.stpmex.com/codi/registraCobro",
            json=lambda *_: deposit_response
            or {
                "estadoPeticion": "0",
                "folioCodi": "123456",
            },
        )

        response = merchant_client.post(
            "/api/payment/v1/stp-codi/deposit/",
            {
                "deposit_type": StpCodiDepositType.APP,
                "amount": "100.00",
                "currency": "MXN",
                "wallet_id": wallet.uuid,
                "customer_id": "customer1",
                "user_data": {
                    "phone": "1234567890",
                },
            },
            format="json",
        )
        assert response.status_code == 201
        return response


class TestStpCodiSystem:
    def test_deposit_success_app(
        self,
        merchant_client,
        api_client,
        merchant,
        wallet_stp_codi,
        mock_on_commit,
        mock_check_status_task,
        mock_send_callback,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://sandbox-api.stpmex.com/codi/registraCobro",
                json=lambda *_: {
                    "estadoPeticion": "0",
                    "folioCodi": "123456",
                },
            )

            response = merchant_client.post(
                "/api/payment/v1/stp-codi/deposit/",
                {
                    "deposit_type": StpCodiDepositType.APP,
                    "amount": "100.00",
                    "currency": "MXN",
                    "wallet_id": wallet_stp_codi.uuid,
                    "customer_id": "customer1",
                    "user_data": {
                        "phone": "1234567890",
                    },
                },
                format="json",
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            assert trx.id_in_payment_system == "123456"
            assert trx.check_status_until
            assert trx.status == TransactionStatus.PENDING

            # Callback
            response = merchant_client.post(
                "/api/payment/v1/callback/stp-codi/",
                data={
                    "estado": "Success",
                    "id": "123456",
                },
                format="json",
            )
            assert response.status_code == 200

            cb = IncomingCallback.objects.get()
            assert cb.status == CallbackStatus.SUCCESS, cb.error

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

            # Transaction status
            response = api_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert trx.customer
            assert response.json() == matchers.DictContains(
                {
                    "amount": "100.00",
                    "currency": "MXN",
                    "customer_id": str(trx.customer.uuid),
                    "status": "success",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "phone": "1234567890",
                        }
                    ),
                }
            )

    def test_deposit_success_app_with_status_check(
        self, merchant_client, wallet_stp_codi
    ):
        make_stp_codi_request(merchant_client, wallet_stp_codi)

        trx = PaymentTransaction.objects.get()

        with requests_mock.Mocker() as m:
            m.post(
                "https://sandbox-api.stpmex.com/codi/cadenaConsultaEstadoOperacion",
                json={
                    "folioCodi": "bf7a99e97e330c59e97e",
                    "historico": False,
                    "estadoCodi": "1",
                    "estadoPeticion": "0",
                },
            )
            tasks.check_status(trx.id)

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

    def test_deposit_fail_app_with_status_check(self, merchant_client, wallet_stp_codi):
        make_stp_codi_request(merchant_client, wallet_stp_codi)

        trx = PaymentTransaction.objects.get()

        with requests_mock.Mocker() as m:
            m.post(
                "https://sandbox-api.stpmex.com/codi/cadenaConsultaEstadoOperacion",
                json={
                    "folioCodi": "c5401ec9b33304bec9b3",
                    "historico": False,
                    "estadoCodi": "-1",
                    "estadoPeticion": "0",
                    "descripcionError": "Error en Registro de Cobro",
                },
            )
            tasks.check_status(trx.id)

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.PENDING
            log: PaymentTransactionEventLog | None = (
                PaymentTransactionEventLog.objects.last()
            )
            assert log
            assert log.extra["response"]["text"] == {
                "descripcionError": "Error en Registro de Cobro",
                "estadoCodi": "-1",
                "estadoPeticion": "0",
                "folioCodi": "c5401ec9b33304bec9b3",
                "historico": False,
            }

    def test_deposit_fail_app_immediate(self, merchant_client, wallet_stp_codi):
        make_stp_codi_request(
            merchant_client,
            wallet_stp_codi,
            deposit_response={"historico": False, "estadoPeticion": "-24"},
        )

        trx = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.FAILED
        assert trx.decline_code == "-24"
        assert trx.decline_reason == "EDO CELLULAR CUSTOMER ERROR NO FUNCTIONS"

    def test_deposit_success_qr_code(
        self,
        merchant_client,
        api_client,
        merchant,
        wallet_stp_codi,
        mock_on_commit,
        mock_check_status_task,
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://sandbox-api.stpmex.com/codi/registraCobroQR",
                json={
                    "TYP": 20,
                    "v": {"DEV": "00000161803561219721/2"},
                    "ic": {"IDC": "32c625f322", "SER": 24120073, "ENC": "big data"},
                    "CRY": "some hash",
                },
            )

            response = merchant_client.post(
                "/api/payment/v1/stp-codi/deposit/",
                {
                    "deposit_type": StpCodiDepositType.QR_CODE,
                    "amount": "100.00",
                    "currency": "MXN",
                    "wallet_id": wallet_stp_codi.uuid,
                    "customer_id": "customer1",
                    "user_data": {
                        "phone": "1234567890",
                    },
                },
                format="json",
            )
            assert response.status_code == 201
            trx = PaymentTransaction.objects.get()

            # TODO: check on prod
            # assert trx.id_in_payment_system == "123456"
            assert trx.check_status_until
            assert trx.status == TransactionStatus.PENDING
            assert trx.extra == {
                "stp_codi_type": "qr_code",
                # TODO: user_data to encrypted extra
                "user_data": {
                    "address": None,
                    "city": None,
                    "country": None,
                    "email": None,
                    "first_name": None,
                    "language": None,
                    "last_name": None,
                    "phone": "1234567890",
                    "province": None,
                    "post_code": None,
                    "state": None,
                    "ip_address": None,
                    "date_of_birth": None,
                },
                "bypass_amount_validation_for": ["deposit"],
            }

            assert trx.instruction
            qr_code_real = trx.instruction["qr_code"]
            trx.instruction["qr_code"] = "some qr code data"
            assert trx.instruction == {
                "qr_code": "some qr code data",
                "type": "instruction_qr_code",
            }

            # decode base 64 and open as image
            qr_code_decoded = base64.b64decode(qr_code_real)
            Image.open(BytesIO(qr_code_decoded))

            # Uncomment to show result
            # qr_code_image.show()

            # Transaction status
            response = api_client.get(
                f"/api/payment/v1/transaction/{trx.uuid}/",
            )
            assert response.status_code == 200
            assert response.json()["instruction"] == {
                "qr_code": mock.ANY,
                "type": "instruction_qr_code",
            }

            # Callback
            response = merchant_client.post(
                "/api/payment/v1/callback/stp-codi/",
                data={
                    "estado": "Success",
                    "id": StpCodiUniqueIds.objects.last().id,  # type: ignore
                },
                format="json",
            )
            assert response.status_code == 200

            cb = IncomingCallback.objects.get()
            assert cb.status == CallbackStatus.SUCCESS, cb.error

            trx.refresh_from_db()
            assert trx.status == TransactionStatus.SUCCESS

    def test_deposit_success_app_sandbox(
        self,
        merchant_sandbox_client,
        mock_send_callback,
        api_client,
        merchant_sandbox,
        wallet_stp_codi_sandbox,
        mock_on_commit,
        mock_check_status_task,
    ):
        response = merchant_sandbox_client.post(
            "/api/payment/v1/stp-codi/deposit/",
            {
                "deposit_type": StpCodiDepositType.APP,
                "amount": "100.00",
                "currency": "MXN",
                "wallet_id": wallet_stp_codi_sandbox.uuid,
                "customer_id": "customer1",
                "user_data": {
                    "phone": "1234567890",
                },
            },
            format="json",
        )
        assert response.status_code == 201
        trx = PaymentTransaction.objects.get()

        assert trx.id_in_payment_system
        assert trx.check_status_until
        assert trx.status == TransactionStatus.SUCCESS

        # Transaction status
        response = api_client.get(
            f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200
        assert trx.customer
        assert response.json() == matchers.DictContains(
            {
                "amount": "100.00",
                "currency": "MXN",
                "customer_id": str(trx.customer.uuid),
                "status": "success",
                "type": "deposit",
                "user_data": matchers.DictContains(
                    {
                        "phone": "1234567890",
                    }
                ),
            }
        )

    def test_deposit_success_qr_code_sandbox(
        self,
        merchant_sandbox_client,
        api_client,
        merchant_sandbox,
        wallet_stp_codi_sandbox,
        mock_on_commit,
        mock_send_callback,
        mock_check_status_task,
    ):
        response = merchant_sandbox_client.post(
            "/api/payment/v1/stp-codi/deposit/",
            {
                "deposit_type": StpCodiDepositType.QR_CODE,
                "amount": "100.00",
                "currency": "MXN",
                "wallet_id": wallet_stp_codi_sandbox.uuid,
                "customer_id": "customer1",
                "user_data": {
                    "phone": "1234567890",
                },
            },
            format="json",
        )
        assert response.status_code == 201
        trx = PaymentTransaction.objects.get()

        # TODO: check on prod
        # assert trx.id_in_payment_system == "123456"
        assert trx.check_status_until
        assert trx.status == TransactionStatus.SUCCESS
        assert trx.extra == {
            "stp_codi_type": "qr_code",
            # TODO: user_data to encrypted extra
            "user_data": {
                "address": None,
                "city": None,
                "country": None,
                "email": None,
                "first_name": None,
                "last_name": None,
                "province": None,
                "language": None,
                "phone": "1234567890",
                "post_code": None,
                "state": None,
                "ip_address": None,
                "date_of_birth": None,
            },
            "bypass_amount_validation_for": ["deposit"],
        }

        assert trx.instruction
        qr_code_real = trx.instruction["qr_code"]
        trx.instruction["qr_code"] = "some qr code data"
        assert trx.instruction == {
            "qr_code": "some qr code data",
            "type": "instruction_qr_code",
        }

        # decode base 64 and open as image
        qr_code_decoded = base64.b64decode(qr_code_real)
        qr_code_image = Image.open(BytesIO(qr_code_decoded))
        assert qr_code_image

        # Uncomment to show result
        # qr_code_image.show()

        # Transaction status
        response = api_client.get(
            f"/api/payment/v1/transaction/{trx.uuid}/",
        )
        assert response.status_code == 200
        assert response.json()["instruction"] == {
            "qr_code": mock.ANY,
            "type": "instruction_qr_code",
        }

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS

    def test_actualization(
        self, wallet_stp_codi, merchant, mock_on_commit, mock_send_callback
    ):
        trx = PaymentTransactionFactory.create(
            wallet__wallet=wallet_stp_codi,
            wallet__wallet__merchant=merchant,
            status=TransactionStatus.PENDING,
            id_in_payment_system="123456",
        )

        with requests_mock.Mocker() as m:
            m.post(
                "https://sandbox-api.stpmex.com/codi/cadenaConsultaEstadoOperacion",
                json={
                    "estadoPeticion": "0",
                    "estadoCodi": "1",
                },
            )
            PaymentTransactionAdmin.do_actualization(
                trx=trx,
                form_data={
                    "actualize": True,
                },
                request_user=UserFactory.create(),
            )

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS


CALLBACK_SUCCESS = {
    "estado": "Success",
    "id": "123456",
}
