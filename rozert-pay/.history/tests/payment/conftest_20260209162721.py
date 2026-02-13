import json
from decimal import Decimal
from typing import Any, Generator, Literal

import pytest
import requests_mock
from django.test.client import Client
from rozert_pay.common.const import PaymentSystemType
from rozert_pay.payment import models
from rozert_pay.payment.models import Bank, PaymentCardBank
from rozert_pay.payment.services import transaction_status_validation
from rozert_pay.payment.systems.bitso_spei.models import BitsoSpeiCardBank
from rozert_pay.payment.systems.stp_codi.client import create_key_pair
from rozert_pay_shared import rozert_client
from tests.factories import CurrencyWalletFactory, WalletFactory


@pytest.fixture
def wallet_paycash(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.PAYCASH,
        system__name="PayCash",
        default_callback_url="https://callbacks",
        credentials=dict(
            host="http://fake.com",
            emisor="fake",
            key="fake",
        ),
    )


@pytest.fixture
def wallet_stp_spei(merchant: models.Merchant, wallet_spei) -> models.Wallet:
    return wallet_spei


@pytest.fixture
def wallet_stp_codi(merchant: models.Merchant) -> models.Wallet:
    private, *_ = create_key_pair("123")

    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.STP_CODI,
        system__name="STP CODI",
        default_callback_url="https://callbacks",
        credentials=dict(
            base_url="https://sandbox-api.stpmex.com",
            tipo_cuenta_beneficiario2=40,
            cuenta_beneficiario2="Reinvent MxLatam",
            qrcode_nombre_beneficiario2="test",
            nombre_beneficiario2="646180301503000001",
            empresa="BETMASTER_MX",
            private_key=private,
            private_key_password="123",
        ),
    )


@pytest.fixture
def wallet_d24_mercadopago(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.D24_MERCADOPAGO,
        system__name="D24 MercadoPago",
        default_callback_url="https://callbacks",
        credentials={
            "base_url": "https://api-stg.directa24.com",
            "base_url_for_credit_cards": "https://cc-api-stg.directa24.com",
            "deposit_signature_key": "",
            "cashout_login": "",
            "cashout_pass": "",
            "cashout_signature_key": "",
            "x_login": "",
        },
    )


@pytest.fixture
def wallet_worldpay(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.WORLDPAY,
        system__name="Worldpay",
        default_callback_url="https://callbacks",
        credentials={
            "base_url": "https://secure-test.worldpay.com",
            "username": "fake_username",
            "password": "fake_password",
            "merchant_code": "fake_merchant_code",
            "jwt_issuer": "fake_jwt_issuer",
            "jwt_org_unit_id": "fake_jwt_org_unit_id",
            "jwt_mac_key": "fake_jwt_mac_key",
            "three_ds_challenge_action_url": "https://centinelapi.cardinalcommerce.com/V2/Cruise/StepUp",
        },
    )


@pytest.fixture
def wallet_worldpay_sandbox(merchant_sandbox: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant_sandbox,
        system__type=PaymentSystemType.WORLDPAY,
        system__name="Worldpay",
        default_callback_url="https://callbacks",
        credentials={
            "base_url": "https://secure-test.worldpay.com",
            "username": "fake_username",
            "password": "fake_password",
            "merchant_code": "fake_merchant_code",
            "jwt_issuer": "fake_jwt_issuer",
            "jwt_org_unit_id": "fake_jwt_org_unit_id",
            "jwt_mac_key": "fake_jwt_mac_key",
            "three_ds_challenge_action_url": "https://centinelapi.cardinalcommerce.com/V2/Cruise/StepUp",
        },
    )


@pytest.fixture
def wallet_stp_codi_sandbox(merchant_sandbox: models.Merchant) -> models.Wallet:
    private, *_ = create_key_pair("123")

    return WalletFactory.create(
        merchant=merchant_sandbox,
        system__type=PaymentSystemType.STP_CODI,
        system__name="STP CODI",
        default_callback_url="https://callbacks",
        credentials=dict(
            base_url="",
            tipo_cuenta_beneficiario2=40,
            cuenta_beneficiario2="",
            qrcode_nombre_beneficiario2="test",
            nombre_beneficiario2="",
            empresa="",
            private_key="",
            private_key_password="123",
        ),
    )


@pytest.fixture
def wallet_d24_mercadopago_sandbox(merchant_sandbox: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant_sandbox,
        system__type=PaymentSystemType.D24_MERCADOPAGO,
        system__name="D24 MercadoPago",
        default_callback_url="https://callbacks",
        credentials={
            "base_url": "https://api-stg.directa24.com",
            "base_url_for_credit_cards": "https://cc-api-stg.directa24.com",
            "deposit_signature_key": "",
            "cashout_login": "",
            "cashout_pass": "",
            "cashout_signature_key": "",
            "x_login": "",
        },
    )


@pytest.fixture
def wallet_paypal(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.PAYPAL,
        system__name="PayPal",
        default_callback_url="https://callbacks",
        credentials={},
    )


@pytest.fixture
def wallet_conekta_oxxo(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.CONEKTA_OXXO,
        system__name="Conekta Oxxo",
        default_callback_url="https://callbacks",
        credentials={
            "api_token": "123456789012",
            "webhook_public_key": "123456789012",
            "base_url": "https://conekta",
        },
    )


@pytest.fixture
def wallet_conekta_oxxo_sandbox(merchant_sandbox: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant_sandbox,
        system__type=PaymentSystemType.CONEKTA_OXXO,
        system__name="Conekta Oxxo",
        default_callback_url="https://callbacks",
        credentials={
            "api_token": "123456789012",
            "webhook_public_key": "123456789012",
            "base_url": "https://conekta",
        },
    )


@pytest.fixture
def wallet_appex(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.APPEX,
        system__name="Appex",
        default_callback_url="https://callbacks",
        credentials={
            "secret1": "fake_secret1",
            "secret2": "fake",
            "account": "fake_account",
            "host": "http://appex",
            "operator": None,
        },
    )


@pytest.fixture
def currency_wallet_paypal(wallet_paypal: models.Wallet) -> models.CurrencyWallet:
    return CurrencyWalletFactory.create(
        wallet=wallet_paypal, operational_balance=Decimal("100.00")
    )


@pytest.fixture
def currency_wallet_d24_mercadopago(
    wallet_d24_mercadopago: models.Wallet,
) -> models.CurrencyWallet:
    return CurrencyWalletFactory.create(
        currency="MXN",
        operational_balance=10000,
        wallet=wallet_d24_mercadopago,
    )


@pytest.fixture
def currency_wallet_d24_mercadopago_sandbox(
    wallet_d24_mercadopago_sandbox: models.Wallet,
) -> models.CurrencyWallet:
    return CurrencyWalletFactory.create(
        currency="MXN",
        operational_balance=10000,
        wallet=wallet_d24_mercadopago_sandbox,
    )


class ExternalTestClient(rozert_client.RozertClient):
    session: Client  # type: ignore

    def __init__(
        self, merchant: models.Merchant, client: Client, sandbox: bool = False
    ):
        super().__init__(
            host="",
            merchant_id=str(merchant.uuid),
            secret_key=merchant.secret_key,
            sandbox=sandbox,
        )
        self.session = client

    def get(self, url: str) -> Any:
        return self._make_request("get", url, data=None)

    def _make_request(
        self,
        method: Literal["get", "post"],
        url: str,
        data: dict[str, Any] | list[Any] | None,
    ) -> dict[str, Any] | list[Any]:
        data_str = data and json.dumps(data, cls=rozert_client.BMJsonEncoder) or ""
        updated_headers = {
            "HTTP_" + key.upper().replace("-", "_"): value
            for key, value in self._get_headers(data_str or "").items()
        }

        resp = self.session.generic(
            method=method,
            path=url,
            data=data and data_str or "",
            content_type="application/json",
            **updated_headers,  # type: ignore
        )
        if resp.status_code >= 400:
            raise Exception(resp.status_code, resp.content)
        return resp.json()


@pytest.fixture
def external_client(merchant, client):
    return ExternalTestClient(merchant, client)


@pytest.fixture
def external_client_sandbox(merchant, client):
    return ExternalTestClient(merchant, client, sandbox=True)


@pytest.fixture
def mock_final_status_validation():
    with transaction_status_validation.disable_final_status_validation():
        yield


@pytest.fixture
def wallet_bitso_spei(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.BITSO_SPEI,
        system__name="Bitso SPEI",
        default_callback_url="https://callbacks",
        credentials={
            "base_api_url": "https://bitsospei",
            "api_key": "fake",
            "api_secret": "fake",
        },
    )


@pytest.fixture
def wallet_muwe_spei(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.MUWE_SPEI,
        system__name="MUWE SPEI",
        default_callback_url="https://callbacks",
        credentials={
            "base_api_url": "https://test.sipelatam.mx",
            "app_id": "fake_app_id_12345",
            "mch_id": "fake_mch_id_67890",
            "api_key": "fake_api_key_abc123xyz456def",
        },
    )


@pytest.fixture
def mock_bitso_api_response() -> Generator[requests_mock.Mocker, None, None]:
    with requests_mock.Mocker() as requests_mocker:
        requests_mocker.get(
            "https://bitso.com/api/v3/banks/MX",
            json={
                "success": True,
                "payload": [
                    {
                        "id": 19,
                        "code": "40072",
                        "name": "BANORTE",
                        "countryCode": "MX",
                        "accountTypes": [],
                        "isActive": True,
                    },
                    {
                        "id": 47,
                        "code": "40154",
                        "name": "BANCO COVALTO",
                        "countryCode": "MX",
                        "accountTypes": [],
                        "isActive": True,
                    },
                    {
                        "id": 22,
                        "code": "40106",
                        "name": "BANK OF AMERICA",
                        "countryCode": "MX",
                        "accountTypes": [],
                        "isActive": True,
                    },
                ],
            },
        )
        yield requests_mocker


@pytest.fixture
def mock_payment_card_banks() -> list[PaymentCardBank]:
    bank1 = Bank.objects.create(name="BANORTE")
    bank2 = Bank.objects.create(name="BANCO COVALTO")
    bank3 = Bank.objects.create(name="BANK OF AMERICA")

    return [
        PaymentCardBank.objects.create(
            bin="012180",
            bank=bank1,
            country="MX",
        ),
        PaymentCardBank.objects.create(
            bin="654321",
            bank=bank2,
            country="MX",
        ),
        PaymentCardBank.objects.create(
            bin="148822",
            bank=bank3,
            country="MX",
        ),
    ]


@pytest.fixture
def mock_existent_bitso_spei_bank() -> BitsoSpeiCardBank:
    return BitsoSpeiCardBank.objects.create(
        code="40012", name="BBVA Bancomer", country_code="MX", is_active=True
    )


@pytest.fixture
def wallet_cardpay_cards(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.CARDPAY_CARDS,
        system__name="Cardpay Cards",
        default_callback_url="https://callbacks",
        credentials={
            "callback_secret": "",
            "terminal_password": "",
            "terminal_code": 123,
        },
    )


@pytest.fixture
def wallet_cardpay_applepay(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.CARDPAY_APPLEPAY,
        system__name="Cardpay Applepay",
        default_callback_url="https://callbacks",
        credentials={
            "callback_secret": "",
            "terminal_password": "",
            "terminal_code": 123,
            "applepay_key": "key",
            "applepay_certificate": "cert",
        },
    )


@pytest.fixture
def wallet_ilixium(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.ILIXIUM,
        system__name="Ilixium",
        default_callback_url="https://callbacks",
        credentials={
            "merchant_id": "fake",
            "account_id": "fake",
            "api_key": "fake",
            "withdrawal_merchant_name": "fake",
            "withdrawal_api_key": "fake",
        },
    )


@pytest.fixture
def wallet_nuvei(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.NUVEI,
        system__name="Nuvei",
        default_callback_url="https://callbacks",
        credentials={
            "merchant_id": "111",
            "merchant_site_id": "777",
            "base_url": "http://nuvei",
            "secret_key": "secret",
        },
    )


@pytest.fixture
def currency_wallet_nuvei(wallet_nuvei: models.Wallet) -> models.CurrencyWallet:
    return CurrencyWalletFactory.create(
        wallet=wallet_nuvei,
        operational_balance=Decimal("1000.00"),
    )


@pytest.fixture
def wallet_mpesa_mz(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.MPESA_MZ,
        system__name="M-Pesa MZ",
        system__slug="mpesa-mz",
        default_callback_url="https://callbacks",
        credentials={
            "api_key": "fake_api_key",
            "public_key": "fake_public_key",
            "service_provider_code": "171717",
            "base_url": "https://api.mpesa.vm.co.mz",
        },
    )


@pytest.fixture
def currency_wallet_mpesa_mz(
    wallet_mpesa_mz: models.Wallet,
) -> models.CurrencyWallet:
    return CurrencyWalletFactory.create(
        currency="MZN",
        operational_balance=Decimal("10000.00"),
        wallet=wallet_mpesa_mz,
    )
