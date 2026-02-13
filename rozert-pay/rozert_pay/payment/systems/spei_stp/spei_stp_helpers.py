import base64
import logging
import random
from decimal import Decimal
from typing import Any, NewType

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from pydantic import BaseModel, SecretStr
from rozert_pay.payment import types
from rozert_pay.payment.models import Wallet
from rozert_pay.payment.systems.spei_stp import spei_stp_const

logger = logging.getLogger(__name__)


def calculate_clabe_check_digit(account_number: str) -> int:
    """See https://stpmex.zendesk.com/hc/en-us/articles/360014675872-Calculation-of-the-CLABE-account-verification-digit"""
    if len(account_number) != 17:
        raise ValueError("Account number must be 18 digits long")

    ponderation = [3, 7, 1] * 6

    step1 = [int(account_number[i]) * ponderation[i] for i in range(17)]
    step2 = [x % 10 for x in step1]
    A = sum(step2)
    A = A % 10
    B = 10 - A
    control_digit = B % 10
    return control_digit


Clabe = NewType("Clabe", str)  # 5 digit clabe number, without account prefix
AccountPrefix = NewType("AccountPrefix", str)  # 12 digit account number prefix
AccountNumber = NewType("AccountNumber", str)  # 18 digit full account number


def to_clabe(val: str | Clabe | int) -> Clabe:
    if isinstance(val, int):
        val = f"{val:05}"

    if len(val) == 18:
        # This is account number
        return to_clabe(val[12:17])

    if not val.isdigit():
        raise ValueError("Clabe must be a number")
    assert len(val) == 5
    if 0 <= int(val) <= 99999:
        return Clabe(val)
    raise ValueError(f"Clabe must be a 5 digit number: {val} received!")


def build_account_number(prefix: AccountPrefix, clabe: Clabe) -> AccountNumber:
    acc = f"{prefix}{clabe}"
    check_digit = calculate_clabe_check_digit(acc)
    return AccountNumber(f"{acc}{check_digit}")


def to_account_prefix(val: str) -> AccountPrefix:
    if len(val) == 18:
        # This is full account number
        return to_account_prefix(val[:12])

    assert len(val) == 12, f"{len(val)}: {val}"
    assert val.isdigit()
    return AccountPrefix(val)


def create_deposit_account_and_spei_transaction_for_user(
    *,
    external_customer_id: types.ExternalCustomerId,
    wallet: Wallet,
    creds: types.T_Credentials,
) -> str:
    assert isinstance(creds, SpeiStpCreds)

    all_plazas = set(range(11, 955))
    free_plaza = random.choice(list(all_plazas))
    mask = creds.account_number_prefix[:12]
    prefix = to_account_prefix(mask[:3] + f"{free_plaza:03}" + mask[6:])
    assert len(prefix) == 12
    random_clabe = random.choice(list(range(1, 100000)))
    return build_account_number(prefix, to_clabe(random_clabe))


class SpeiStpCreds(BaseModel):
    account_number_prefix: str
    base_url: str
    withdrawal_target_account: str
    check_api_base_url: str
    private_key: SecretStr
    private_key_password: SecretStr


class SpeiCallbackError(RuntimeError):
    id: int
    message: str

    def to_payload(self) -> dict[str, Any]:
        return {"id": self.id, "message": self.message}

    def __init__(
        self,
        id: int,
        message: str,
    ) -> None:
        self.id = id
        self.message = message


class SpeiStpTransactionAlreadyExist(Exception):
    pass


def get_clabe_from_deposit_account(deposit_account: str) -> str:
    return deposit_account[-6:-1]


def spei_deposit_id_in_payment_system(payload: dict[str, Any]) -> str:
    return f"{payload['claveRastreo']}:{payload['id']}"


def spei_deposit_wallet_account(payload: dict[str, Any]) -> str:
    return str(payload["cuentaOrdenante"])


def get_data_signature(data: str, creds: SpeiStpCreds) -> str:
    private_key = serialization.load_pem_private_key(
        creds.private_key.get_secret_value().encode(),
        password=creds.private_key_password.get_secret_value().encode(),
    )
    sign_bytes = private_key.sign(data.encode(), padding.PKCS1v15(), hashes.SHA256())  # type: ignore
    signature_b64 = base64.b64encode(sign_bytes)
    sign = signature_b64.decode("utf-8")
    logger.info(
        "signed payload for spei_stp",
        extra={
            "payload": data,
            "signature": sign,
        },
    )
    return sign


def get_withdraw_payload(
    trx_uuid: str,
    description: str,
    target_account: str,
    from_account: str,
    institution_contraparte: str,
    amount: Decimal,
) -> dict[str, Any]:
    assert amount > 0, amount
    assert target_account, target_account

    result = {
        "claveRastreo": trx_uuid,
        "conceptoPago": description[:39],
        "cuentaOrdenante": from_account,
        "cuentaBeneficiario": target_account,
        "empresa": spei_stp_const.PAYOUT_EMPRESA,
        "institucionContraparte": institution_contraparte,
        "institucionOperante": "90646",
        "monto": str(amount.quantize(Decimal("1.00"))),
        "nombreBeneficiario": "S.A. de C.V.",
        "nombreOrdenante": "REINVENT MXLATAM SA DE CV",
        "referenciaNumerica": "123456",
        "rfcCurpBeneficiario": "ND",
        "rfcCurpOrdenante": "ND",
        "tipoCuentaBeneficiario": "40",
        "tipoCuentaOrdenante": "40",
        "tipoPago": "1",
    }
    if len(target_account) != 18:
        logger.info(
            "cuentaBeneficiario not equals 18 symbols, update tipoCuentaBeneficiario"
        )
        result["tipoCuentaBeneficiario"] = "3"
    return result


def sign_payload_for_payout(payload: dict[str, Any]) -> str:
    return (
        f"||{payload['institucionContraparte']}|{payload['empresa']}|||{payload['claveRastreo']}"
        f"|{payload['institucionOperante']}|{payload['monto']}|{payload['tipoPago']}"
        f"|{payload['tipoCuentaOrdenante']}|{payload['nombreOrdenante']}|{payload['cuentaOrdenante']}"
        f"|{payload['rfcCurpOrdenante']}|{payload['tipoCuentaBeneficiario']}"
        f"|{payload['nombreBeneficiario']}|{payload['cuentaBeneficiario']}"
        f"|{payload['rfcCurpBeneficiario']}||||||{payload['conceptoPago']}"
        f"||||||{payload['referenciaNumerica']}||||||||"
    )
