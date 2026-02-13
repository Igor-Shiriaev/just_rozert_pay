import contextlib
import random
import re
import typing
from decimal import Decimal
from typing import Any, Generator, Literal, Optional, Union
from unittest import mock
from unittest.mock import patch

import pytest
import requests_mock
from django.test import Client
from pydantic import BaseModel
from rozert_pay.common import const
from rozert_pay.common.const import (
    PaymentSystemType,
    TransactionStatus,
    TransactionType,
)
from rozert_pay.payment import entities, models, types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.extra_fields import wallet_extra_fields
from rozert_pay.payment.models import (
    CurrencyWallet,
    Customer,
    CustomerExternalPaymentSystemAccount,
    OutcomingCallback,
    PaymentTransaction,
)
from rozert_pay.payment.services import db_services
from rozert_pay.payment.systems.spei_stp import spei_stp_helpers
from rozert_pay.payment.systems.spei_stp.spei_stp_client import SpeiStpClient
from tests.factories import CurrencyWalletFactory, PaymentTransactionFactory


class MockBehaviourContainer(BaseModel):
    behaviour: Literal["success", "decline"] = "success"
    decline_code: str = "DECLINE_CODE"
    payout_response: Optional[dict[str, Any]] = None
    status_response: Optional[dict[str, Any]] = None
    status_response_code: int = 200


SPEI_STP_ACCOUNT_NUMBER_PREFIX = "646010525503"
SPEI_WITHDRAWAL_TARGET_ACCOUNT = "646180525503000001"
SPEI_STP_BASE_URL = "https://demo.stpmex.com:7024"
STP_SPEI_CHECK_API_BASE_URL = "https://efws-dev.stpmex.com"


def get_deposit_account_for_clabe(clabe: Union[str, int], prefix: str) -> str:
    return spei_stp_helpers.build_account_number(
        prefix=spei_stp_helpers.to_account_prefix(prefix),
        clabe=spei_stp_helpers.to_clabe(clabe),
    )


ID_IN_PAYMENT_SYSTEM = "123123123"


@contextlib.contextmanager
def mock_requests(
    behaviour_container=MockBehaviourContainer(),
):
    with requests_mock.Mocker() as m:

        def _payout(*a, **k):
            return behaviour_container.payout_response or {
                "resultado": {
                    "id": ID_IN_PAYMENT_SYSTEM,
                    "descripcionError": None,
                }
            }

        def _status(*a, **k):
            trx: typing.Any = PaymentTransaction.objects.last()
            assert trx
            return behaviour_container.status_response or {
                "datos": [
                    {
                        "estado": "success",
                        "idEF": trx.id_in_payment_system,
                        "monto": str(-trx.amount_foreign),
                    }
                ]
            }

        m.put(url=re.compile("/speiws/rest/ordenPago/registra"), json=_payout)
        m.get(
            url=re.compile("/efws/API/consultaOrden"),
            json=_status,
        )
        m.post(
            url=re.compile("/api/notify/single"),
            text="",
        )
        yield m


STP_CALLBACK_BASE = {
    "id": 3191365,
    "fechaOperacion": 20200127,
    "institucionOrdenante": 846,
    "institucionBeneficiaria": 90646,
    "claveRastreo": "12345",
    "monto": 0.01,
    "nombreOrdenante": "STP",
    "tipoCuentaOrdenante": 40,
    "cuentaOrdenante": "846180000400000001",
    "rfcCurpOrdenante": "ND",
    "nombreBeneficiario": "NOMBRE_DE_BENEFICIARIO",
    "tipoCuentaBeneficiario": 40,
    "cuentaBeneficiario": "64618012340000000D",
    "nombreBeneficiario2": "NOMBRE_DE_BENEFICIARIO2",
    "tipoCuentaBeneficiario2": 40,
    "cuentaBeneficiario2": "64618012340000000D",
    "rfcCurpBeneficiario": "ND",
    "conceptoPago": "PRUEBA1",
    "referenciaNumerica": 1234567,
    "empresa": "NOMBRE_EMPRESA",
    "tipoPago": 1,
    "tsLiquidacion": "1634919027297",
    "folioCodi": "f4c1111abd2b28a00abc",
}
stp_callback_with_folio_origen: dict[str, str] = {
    "causaDevolucion": "",
    "empresa": "BETMASTER_MX",
    "estado": "Success",
    "folioOrigen": "86de4d8710404d4194021f5c54ff98",
    "id": "1128175285",
    "tsLiquidacion": "1718460204576",
}


@contextlib.contextmanager
def patch_find_institucionOrdenante_for_wallet():
    with patch(
        "payment.base_v2.systems.spei_stp.find_institucionOrdenante_for_wallet",
        return_value="1234",
    ) as m:
        yield m


@pytest.fixture
def spei_deposit_account(wallet_spei) -> models.CustomerDepositInstruction:
    return db_services.create_customer_deposit_instruction(
        system_type=PaymentSystemType.STP_SPEI,
        external_customer_id=types.ExternalCustomerId("customer1"),
        deposit_account_number="646180110400000001",
        wallet=wallet_spei,
    )


@pytest.fixture
def customer_external_account(wallet_spei) -> CustomerExternalPaymentSystemAccount:
    w = db_services.create_customer_external_payment_system_account(
        external_customer_id="customer1",
        account_number="646180110400000007",
        system_type=PaymentSystemType.STP_SPEI,
        wallet_id=types.WalletId(wallet_spei.id),
    )
    w.extra[wallet_extra_fields.INSTITUTION_ORDENANTE] = "1234"
    w.save()
    return w


class TestSpeiStpFlow:
    @pytest.fixture
    def c(
        self,
        db,
        merchant_client,
        merchant,
        mock_send_callback,
        wallet_spei,
    ) -> Generator[Client, None, None]:
        self.mock_behaviour = MockBehaviourContainer()
        with (mock_requests(self.mock_behaviour) as self.mock_requests,):
            yield merchant_client

    def test_deposit_new_flow_success(self, c, wallet_stp_spei, client):
        random.seed(42)

        resp = c.post(
            "/api/payment/v1/stp-spei/create_instruction/",
            {
                "wallet_id": wallet_stp_spei.uuid,
                "customer_id": "customer1",
                "redirect_url": "http://google.com",
            },
            format="json",
        )
        assert resp.status_code == 200, resp.json()
        customer = Customer.objects.get()
        assert resp.json() == {
            "deposit_account": "123665789012145936",
            "customer_id": str(customer.uuid),
        }

        # Same customer should get same account
        resp = c.post(
            "/api/payment/v1/stp-spei/create_instruction/",
            {
                "wallet_id": wallet_stp_spei.uuid,
                "customer_id": "customer1",
            },
            format="json",
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json() == {
            "deposit_account": "123665789012145936",
            "customer_id": str(customer.uuid),
        }

        # another customer - new account
        resp = c.post(
            "/api/payment/v1/stp-spei/create_instruction/",
            {
                "wallet_id": wallet_stp_spei.uuid,
                "customer_id": "customer2",
            },
            format="json",
        )
        customer2 = Customer.objects.last()
        assert customer2
        assert customer2 != customer
        assert resp.status_code == 200, resp.json()
        assert resp.json() == {
            "deposit_account": "123036789012971975",
            "customer_id": str(customer2.uuid),
        }

        # Confirmation callback
        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                **STP_CALLBACK_BASE,
                # customer 1 deposit
                "cuentaBeneficiario": "123665789012145936",
                "monto": "123.12",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        # duplicate confirmation callback - no effect
        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                **STP_CALLBACK_BASE,
                # customer 1 deposit
                "cuentaBeneficiario": "123665789012145936",
                "monto": "123.12",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        assert PaymentTransaction.objects.count() == 1
        trx: PaymentTransaction = PaymentTransaction.objects.last()  # type: ignore
        assert trx
        assert trx.customer_instruction
        assert trx.status == entities.TransactionStatus.SUCCESS
        assert trx.customer_instruction.customer.external_id == "customer1"
        assert trx.customer == trx.customer_instruction.customer
        assert trx.customer_external_account
        assert (
            trx.customer_external_account.unique_account_number == "846180000400000001"
        )
        assert trx.customer_instruction and trx.customer_external_account
        assert trx.customer_instruction.deposit_account_number == "123665789012145936"
        assert trx.customer_external_account.customer == trx.customer
        assert OutcomingCallback.objects.count() == 1
        assert trx.customer_external_account.extra == {
            "spei_institution_ordenante": "846"
        }

        cb = OutcomingCallback.objects.get()
        assert cb.body == {
            "amount": "123.12",
            "callback_url": None,
            "card_token": None,
            "created_at": mock.ANY,
            "currency": "MXN",
            "customer_id": str(trx.customer.uuid),
            "decline_code": None,
            "decline_reason": None,
            "external_account_id": "846180000400000001",
            "external_customer_id": str(trx.customer.external_id),
            "form": None,
            "id": str(trx.uuid),
            "instruction": None,
            "status": "pending",
            "type": "deposit",
            "updated_at": mock.ANY,
            "user_data": mock.ANY,
            "wallet_id": str(trx.wallet.wallet.uuid),
        }

    def test_clabe_check_digit(self):
        account_number = "00218003224094670"
        control_digit = spei_stp_helpers.calculate_clabe_check_digit(account_number)
        assert control_digit == 0

    def test_withdraw_sign_payload(self):
        p = spei_stp_helpers.get_withdraw_payload(
            trx_uuid="test1",
            description="test REST",
            amount=Decimal("0.01"),
            target_account="646180110400000007",
            from_account="646180301503000001",
            institution_contraparte="123",
        )
        assert (
            spei_stp_helpers.sign_payload_for_payout(p)
            == "||123|BETMASTER_MX|||test1|90646|0.01|1|40|REINVENT MXLATAM SA DE CV|646180301503000001|ND|40|S.A. de C.V.|646180110400000007|ND||||||test REST||||||123456||||||||"
        )

    def test_callback_clabe_not_found_refund_response(self, c, client):
        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                **STP_CALLBACK_BASE,
                "cuentaBeneficiario": "646180110400000012",
                "monto": "10",
            },
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.json() == {"id": 2, "message": "No customer instruction found"}

    def test_callback_amount_changed_success(
        self, c, client, spei_deposit_account, mock_send_callback
    ):
        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                **STP_CALLBACK_BASE,
                "cuentaBeneficiario": spei_deposit_account.deposit_account_number,
                "monto": "2000",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200

        trx: PaymentTransaction = PaymentTransaction.objects.last()  # type: ignore
        assert trx
        assert trx.status == "success"
        assert trx.amount == Decimal("2000.00")
        cv = CurrencyWallet.objects.get()
        assert cv.available_balance == Decimal("2000.00")

    def test_callback_error(self, c, client, wallet_spei, disable_error_logs):
        trx = PaymentTransactionFactory.create(
            type=TransactionType.WITHDRAWAL,
            wallet__wallet=wallet_spei,
            extra={
                "id": 1541917838,
            },
        )

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "causaDevolucion": "",
                "empresa": "BETMASTER_MX",
                "estado": "Cancel",
                "folioOrigen": "477f33b1fbb24dff9f3e7d0e5c7656",
                "id": 1541917838,
                "tsLiquidacion": "0",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.FAILED
        assert trx.decline_code == "Cancel"

    def test_callback_no_transaction_initiated(
        self, c, client, wallet_spei, spei_deposit_account
    ):
        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                **STP_CALLBACK_BASE,
                "cuentaBeneficiario": spei_deposit_account.deposit_account_number,
                "monto": "2000",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200

        assert PaymentTransaction.objects.count() == 1
        trx = PaymentTransaction.objects.last()  # type: ignore
        assert trx
        assert trx.status == const.TransactionStatus.SUCCESS
        assert trx.amount == Decimal("2000.00")
        assert trx.currency == "MXN"

        cv = CurrencyWallet.objects.get()
        assert cv.available_balance == Decimal("2000.00")

    def test_callback_with_error(self, c, client, disable_error_logs):
        resp = client.post(
            "/api/ps/stp-spei/",
            data={},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.json() == {"id": 2, "message": "Error during callback processing"}

    def test_callback_for_existing_deposit(self, c, client, wallet_spei):
        trx = PaymentTransactionFactory.create(
            type=TransactionType.DEPOSIT,
            wallet__wallet=wallet_spei,
            status=const.TransactionStatus.SUCCESS,
            id_in_payment_system="12345:3191365",
            currency="MXN",
            amount=10,
        )

        assert trx.id_in_payment_system

        assert PaymentTransaction.objects.count() == 1
        assert PaymentTransaction.objects.get() == trx

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                **STP_CALLBACK_BASE,
                "monto": "10",
                "claveRastreo": "12345",
                "id": "3191365",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}
        assert PaymentTransaction.objects.count() == 1

    def test_withdraw(
        self,
        c,
        client,
        wallet_spei,
        customer_external_account: CustomerExternalPaymentSystemAccount,
    ):
        CurrencyWalletFactory.create(
            wallet=wallet_spei, hold_balance=10000, balance=10000, currency="MXN"
        )

        resp = c.post(
            "/api/payment/v1/stp-spei/withdraw/",
            data={
                "wallet_id": str(wallet_spei.uuid),
                "amount": "100.00",
                "currency": "MXN",
                "withdraw_to_account": customer_external_account.unique_account_number,
            },
            format="json",
        )
        assert resp.status_code == 201
        trx = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.PENDING
        assert trx.type == TransactionType.WITHDRAWAL
        assert trx.amount == Decimal("100.00")
        assert trx.currency == "MXN"
        assert trx.customer
        assert trx.customer_external_account
        assert trx.customer == trx.customer_external_account.customer
        assert (
            trx.customer_external_account.unique_account_number == "646180110400000007"
        )

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "causaDevolucion": "",
                "empresa": "BETMASTER",
                "estado": "Success",
                "folioOrigen": str(trx.uuid.hex)[:-2],
                "id": ID_IN_PAYMENT_SYSTEM,
                "tsLiquidacion": "1704800378237",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS

    def test_payout_callback(self, c, client, wallet_spei, customer_external_account):
        CurrencyWalletFactory.create(
            wallet=wallet_spei, hold_balance=10000, balance=10000, currency="MXN"
        )

        resp = c.post(
            "/api/payment/v1/stp-spei/withdraw/",
            data={
                "wallet_id": str(wallet_spei.uuid),
                "amount": "100.00",
                "currency": "MXN",
                "withdraw_to_account": "646180110400000007",
            },
            format="json",
        )
        assert resp.status_code == 201
        trx = PaymentTransaction.objects.get()
        assert trx.status == const.TransactionStatus.PENDING
        assert trx.type == TransactionType.WITHDRAWAL
        assert trx.amount == Decimal("100.00")
        assert trx.currency == "MXN"

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "causaDevolucion": "",
                "empresa": "BETMASTER",
                "estado": "Success",
                "folioOrigen": str(trx.uuid.hex)[:-2],
                "id": ID_IN_PAYMENT_SYSTEM,
                "tsLiquidacion": "1701778057160",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.SUCCESS

    def test_payout_callback_decline(
        self, c, client, wallet_spei, customer_external_account
    ):
        CurrencyWalletFactory.create(
            wallet=wallet_spei, hold_balance=10000, balance=10000, currency="MXN"
        )

        resp = c.post(
            "/api/payment/v1/stp-spei/withdraw/",
            data={
                "wallet_id": str(wallet_spei.uuid),
                "amount": "100.00",
                "currency": "MXN",
                "withdraw_to_account": "646180110400000007",
            },
            format="json",
        )
        assert resp.status_code == 201
        trx = PaymentTransaction.objects.get()
        assert trx.status == const.TransactionStatus.PENDING
        assert trx.type == TransactionType.WITHDRAWAL
        assert trx.amount == Decimal("100.00")
        assert trx.currency == "MXN"

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "id": str("123123123"),
                "folioOrigen": str(trx.uuid.hex)[:-2],
                "causaDevolucion": "decline reason",
                "estado": "Decline",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200

        trx.refresh_from_db()
        assert trx.status == const.TransactionStatus.FAILED
        assert trx.decline_code == trx.decline_reason == "decline reason"

    def test_client_get_transaction_status_method(self, db, wallet_spei):
        trx = PaymentTransactionFactory.create(
            type=TransactionType.WITHDRAWAL,
            wallet__wallet=wallet_spei,
        )
        client = SpeiStpClient(trx.id)
        with requests_mock.Mocker() as m:
            m.post(
                "http://spei/efws/API/consultaOrden",
                json={
                    "estado": 6,
                    "mensaje": "No se encontraron datos relacionados",
                },
            )

            resp = client.get_transaction_status()
            assert isinstance(resp, RemoteTransactionStatus)
            resp.raw_data = {}
            assert resp.model_dump(exclude_none=True) == {
                "operation_status": TransactionStatus.PENDING,
                "raw_data": {},
            }

            m.post(
                "http://spei/efws/API/consultaOrden",
                json={
                    "estado": 0,
                    "mensaje": "Datos consultados correctamente",
                    "respuesta": {
                        "idEF": 867626005,
                        "monto": "101.13",
                    },
                },
            )
            resp = client.get_transaction_status()
            assert isinstance(resp, RemoteTransactionStatus)
            resp.raw_data = {}
            assert resp.model_dump(exclude_none=True) == {
                "id_in_payment_system": "867626005",
                "operation_status": TransactionStatus.PENDING,
                "raw_data": {},
                "remote_amount": {"currency": "USD", "value": Decimal("101.13")},
            }

    def test_refund(self, c, client, wallet_spei, customer_external_account):
        w: CurrencyWallet = CurrencyWalletFactory.create(
            wallet=wallet_spei, hold_balance=10000, balance=10000, currency="MXN"
        )

        resp = c.post(
            "/api/payment/v1/stp-spei/withdraw/",
            data={
                "wallet_id": str(wallet_spei.uuid),
                "amount": "100.00",
                "currency": "MXN",
                "withdraw_to_account": "646180110400000007",
            },
            format="json",
        )
        assert resp.status_code == 201
        trx = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.PENDING
        assert trx.type == TransactionType.WITHDRAWAL
        assert trx.amount == Decimal("100.00")
        assert trx.currency == "MXN"

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "causaDevolucion": "'Excede el límite de abonos permitidos en el mes en la cuenta'",
                "empresa": "BETMASTER",
                "estado": "Refund",
                "folioOrigen": str(trx.uuid.hex)[:-2],
                "id": int(ID_IN_PAYMENT_SYSTEM),
                "tsLiquidacion": "'1704800378237'",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.FAILED
        w.refresh_from_db()
        assert w.hold_balance == Decimal("10000")
        assert w.balance == Decimal("10000")
        assert (
            trx.decline_code
            == "'Excede el límite de abonos permitidos en el mes en la cuenta'"
        )
        assert (
            trx.decline_reason
            == "'Excede el límite de abonos permitidos en el mes en la cuenta'"
        )

    def test_graceful_error_while_getting_trx_by_non_existent_folio_origen_uuid(
        self,
        c,
        client,
        wallet_spei,
        customer_external_account,
    ):
        CurrencyWalletFactory.create(
            wallet=wallet_spei, hold_balance=10000, balance=10000, currency="MXN"
        )

        resp = c.post(
            "/api/payment/v1/stp-spei/withdraw/",
            data={
                "wallet_id": str(wallet_spei.uuid),
                "amount": "100.00",
                "currency": "MXN",
                "withdraw_to_account": "646180110400000007",
            },
            format="json",
        )
        assert resp.status_code == 201
        trx = PaymentTransaction.objects.get()
        assert trx.status == TransactionStatus.PENDING
        assert trx.type == TransactionType.WITHDRAWAL
        assert trx.amount == Decimal("100.00")
        assert trx.currency == "MXN"

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "causaDevolucion": "",
                "empresa": "BETMASTER_MX",
                "estado": "Success",
                "folioOrigen": "non_existent_folio",
                "id": "1128175285",
                "tsLiquidacion": "1718460204576",
            },
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.json() == {"id": 2, "message": "Invalid deposit account"}

    def test_two_callbacks_with_the_same_clave_rastreo(
        self, c, client, wallet_spei, spei_deposit_account
    ):
        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "claveRastreo": "HSBC563680",
                "conceptoPago": "Transferencia SPEI",
                "cuentaBeneficiario": spei_deposit_account.deposit_account_number,
                "cuentaOrdenante": "021075064952814996",
                "id": 989197991,
                "monto": 54,
                "referenciaNumerica": 10524,
                "tsLiquidacion": "1714607394525",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        trx = PaymentTransaction.objects.order_by("created_at").last()
        assert trx

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS
        assert trx.amount == Decimal("54.00")
        assert trx.extra["claveRastreo"] == "HSBC563680"
        assert trx.id_in_payment_system == "HSBC563680:989197991"

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "claveRastreo": "HSBC563680",
                "conceptoPago": "Transferencia SPEI",
                "cuentaBeneficiario": spei_deposit_account.deposit_account_number,
                "cuentaOrdenante": "021168065457009112",
                "id": 1048671747,
                "monto": 54,
                "referenciaNumerica": 10524,
                "tsLiquidacion": "1714607394525",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        assert PaymentTransaction.objects.count() == 2
        trx = PaymentTransaction.objects.order_by("created_at").last()
        assert trx
        assert trx.status == TransactionStatus.SUCCESS
        assert trx.amount == Decimal("54.00")
        assert trx.extra["claveRastreo"] == "HSBC563680"
        assert trx.id_in_payment_system == "HSBC563680:1048671747"

    def test_update_prefix(self, c, client, wallet_spei, spei_deposit_account):
        CurrencyWalletFactory.create(
            wallet=wallet_spei, hold_balance=10000, balance=10000, currency="MXN"
        )

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "claveRastreo": "HSBC563680",
                "conceptoPago": "Transferencia SPEI",
                "cuentaBeneficiario": spei_deposit_account.deposit_account_number,
                "cuentaOrdenante": "021075064952814996",
                "id": 989197991,
                "monto": 54,
                "referenciaNumerica": 10524,
                "tsLiquidacion": "1714607394525",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        trx = PaymentTransaction.objects.order_by("created_at").last()
        assert trx
        assert trx.status == TransactionStatus.SUCCESS
        assert trx.amount == Decimal("54.00")
        assert trx.extra["claveRastreo"] == "HSBC563680"
        assert trx.id_in_payment_system == "HSBC563680:989197991"

        resp = client.post(
            "/api/ps/stp-spei/",
            data={
                "claveRastreo": "HSBC563680",
                "conceptoPago": "Transferencia SPEI",
                "cuentaBeneficiario": spei_deposit_account.deposit_account_number,
                "cuentaOrdenante": "021168065457009112",
                "id": 1048671747,
                "monto": 54,
                "referenciaNumerica": 10524,
                "tsLiquidacion": "1714607394525",
            },
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "recibido"}

        assert PaymentTransaction.objects.count() == 2
        trx = PaymentTransaction.objects.order_by("created_at").last()
        assert trx
        assert trx.status == TransactionStatus.SUCCESS
        assert trx.amount == Decimal("54.00")
        assert trx.extra["claveRastreo"] == "HSBC563680"
        assert trx.id_in_payment_system == "HSBC563680:1048671747"

    def test_get_deposit_account_for_clabe(
        self, c, client, wallet_spei, spei_deposit_account
    ):
        CurrencyWalletFactory.create(
            wallet=wallet_spei, hold_balance=10000, balance=10000, currency="MXN"
        )

        prefix = "1" * 12
        assert get_deposit_account_for_clabe(1, prefix=prefix) == "111111111111000019"
        assert get_deposit_account_for_clabe(2, prefix=prefix) == "111111111111000022"
        assert (
            get_deposit_account_for_clabe(1, SPEI_STP_ACCOUNT_NUMBER_PREFIX)
            == "646010525503000012"
        )
