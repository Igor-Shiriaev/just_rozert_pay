import base64
from io import BytesIO
from unittest import mock

import requests_mock
from PIL import Image
from rozert_pay.common.const import CallbackStatus, TransactionStatus
from rozert_pay.payment.admin import PaymentTransactionAdmin
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.systems.stp_codi.entities import StpCodiDepositType
from tests.factories import PaymentTransactionFactory, UserFactory
from tests.payment.api_v1 import matchers

DEPOSIT_BASE_URL = 'https://deposit.api'
WITHDRAWAL_AND_STATUS_BASE_URL = 'https://remain.api'
CURRENCY = 'MXN'
DEPOSIT_FOREIGN_ID = '301524253'
DEPOSIT_FOREIGN_ID2 = 'deposit_foreign_id2'
WITHDRAWAL_FOREIGN_ID = 'withdrawal_foreign_id'
AMOUNT = '100'
CURRENCY = 'MXN'
MEXICAN_VALID_CURP = 'ssss001230mlllllj0'
MEXICAN_VALID_CURP2 = 'ssss911230mlllllj0'
VALID_CLABE = "021790064060296642"


class TestD24MercadoPagoSystem:
    def test_deposit_success(
        self, merchant_client, api_client, merchant, wallet_stp_codi, mock_on_commit
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://api-stg.directa24.com/v3/deposits",
                json={
                    "checkout_type": "ONE_SHOT",
                    "redirect_url": "https://payment-stg.depositcheckout.com/v1/checkout/eyJhbGciOiJIUzM4NCJ9.eyJqdGkiOiI1NzE4MjMzMiIsImlhdCI6MTc0MDIxMjM1MCwiZXhwIjoxNzQxNTA4MzUwLCJsYW5ndWFnZSI6ImVzIn0.ucf2BY2jZY9brgZdj4tRvI_1cwSgOOcCaRdWezOmvA5wnb7bAU-HgNTg_KTtcfPl/MX/ME/3541/19502",
                    "iframe": True,
                    "deposit_id": DEPOSIT_FOREIGN_ID,
                    "user_id": "62dd744c-cbfa-4357-8ef0-460390e78b5c",
                    "merchant_invoice_id": "postmanTest907958248",
                    "payment_info": {
                        "type": "VOUCHER",
                        "payment_method": "ME",
                        "payment_method_name": "Mercado Pago Mexico",
                        "amount": AMOUNT,
                        "currency": CURRENCY,
                        "expiration_date": "2025-02-22 20:19:10",
                        "created_at": "2025-02-22 08:19:10",
                        "metadata": {
                            "reference": '57182332',
                            "payment_method_code": "ME",
                            "enabled_redirect": True
                        }
                    }
                },
            )

            response = merchant_client.post(
                "/api/payment/v1/d24-mercadopago/deposit/",
                {
                    "amount": "100.00",
                    "currency": "MXN",
                    "wallet_id": wallet_stp_codi.uuid,
                    "customer_id": "customer1",
                    "user_data": {
                        "country": "MX",
                        "email": "test@test.com",
                        "first_name": "John",
                        "last_name": "Doe",
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
                data=CALLBACK_SUCCESS,
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
            assert response.json() == matchers.DictContains(
                {
                    "amount": "100.00",
                    "currency": "MXN",
                    "customer_id": "customer1",
                    "status": "success",
                    "type": "deposit",
                    "user_data": matchers.DictContains(
                        {
                            "phone": "1234567890",
                        }
                    ),
                }
            )

    def test_deposit_success_qr_code(
        self, merchant_client, api_client, merchant, wallet_stp_codi, mock_on_commit
    ):
        with requests_mock.Mocker() as m:
            m.post(
                "https://sandbox-api.stpmex.com/codi/registraCobro",
                json={
                    "estadoPeticion": 0,
                    "folioCodi": "123456",
                    "resultado": "some qr code data",
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
                    "last_name": None,
                    "phone": "1234567890",
                    "post_code": None,
                    "state": None,
                },
                "withdraw_to_account": None,
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
                data=CALLBACK_SUCCESS,
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
        assert response.json() == matchers.DictContains(
            {
                "amount": "100.00",
                "currency": "MXN",
                "customer_id": "customer1",
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
                "phone": "1234567890",
                "post_code": None,
                "state": None,
            },
            "withdraw_to_account": None,
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

    def test_actualization(self, wallet_stp_codi, merchant, mock_on_commit):
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
                    "estadoPeticion": 0,
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
