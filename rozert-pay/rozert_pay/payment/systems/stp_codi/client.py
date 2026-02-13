import base64
import logging
from typing import Any, Literal
from uuid import uuid4

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from OpenSSL import crypto
from rozert_pay.payment import entities
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.services.base_classes import (
    BasePaymentClient,
    BaseSandboxClientMixin,
)
from rozert_pay.payment.systems.stp_codi.const import (
    STP_CODI_ESTADO_PETICION_CODES_TO_DESCRIPTION,
)
from rozert_pay.payment.systems.stp_codi.entities import StpCodiCredentials
from rozert_pay.payment.systems.stp_codi.models import get_or_create_unique_id

logger = logging.getLogger(__name__)


class StpCodiClient(BasePaymentClient[StpCodiCredentials]):
    credentials_cls = StpCodiCredentials

    REMOTE_STATUS_SUCCESS = "0"

    @classmethod
    def _deposit(
        cls,
        *,
        phone: str,
        deposit_type: Literal["app", "qr"],
        amount: str,
        unique_transaction_id: int,
        trx_uuid: str,
        creds: StpCodiCredentials,
        session: requests.Session,
    ) -> dict[str, Any]:
        assert len(str(unique_transaction_id)) <= 7

        phone = phone[3:]
        if deposit_type == "app":
            # See https://stpmex.zendesk.com/hc/en-us/articles/360060547812-Register-Non-Presential-Collection

            # WARNING: Order of fields is important here
            payload: dict[str, str] = {
                "numeroCelularCliente": phone,
                "monto": amount,
                "numeroReferenciaComercio": str(unique_transaction_id),
                "cuentaBeneficiario2": creds.cuenta_beneficiario2,
                "nombreBeneficiario2": creds.nombre_beneficiario2,
                "tipoCuentaBeneficiario2": str(creds.tipo_cuenta_beneficiario2),
                "concepto": f"Order {trx_uuid.split('-')[0]}",
                "empresa": creds.empresa,
                "minutosLimite": "115",
                "tipoPagoDeSpei": "20",
            }
            signature_columns = [
                "numeroCelularCliente",
                "monto",
                "numeroReferenciaComercio",
                "cuentaBeneficiario2",
                "nombreBeneficiario2",
                "tipoCuentaBeneficiario2",
                "concepto",
                "empresa",
                "minutosLimite",
                "tipoPagoDeSpei",
            ]

        elif deposit_type == "qr":
            # See https://stpmex.zendesk.com/hc/en-us/articles/360053021391-Register-QR-Collection
            payload = {
                "numeroReferenciaComercio": str(unique_transaction_id),
                "concepto": f"Order {trx_uuid.split('-')[0]}",
                "minutosLimite": "500",
                "monto": amount,
                "nombreBeneficiario": creds.qrcode_nombre_beneficiario2,
                "tipoCuentaBeneficiario": str(creds.tipo_cuenta_beneficiario2),
                "cuentaBeneficiario": creds.cuenta_beneficiario2,
                "bancoBeneficiario": "90646",
                "empresa": creds.empresa,
                "tipoPagoDeSpei": "20",
            }

            signature_columns = [
                "numeroReferenciaComercio",
                "concepto",
                "minutosLimite",
                "monto",
                "nombreBeneficiario",
                "bancoBeneficiario",
                "tipoCuentaBeneficiario",
                "cuentaBeneficiario",
                "empresa",
                "tipoPagoDeSpei",
            ]
        else:
            raise

        payload["firma"] = StpCodiClient.get_stp_signature(
            payload,
            signature_columns,
            private_key=creds.private_key.get_secret_value(),
            private_key_password=creds.private_key_password.get_secret_value(),
        )

        url = {
            "qr": "/codi/registraCobroQR",
            "app": "/codi/registraCobro",
        }[deposit_type]

        resp = session.post(
            f"{creds.base_url}{url}",
            json=payload,
        )
        return resp.json()

    def deposit_qr_code(self) -> entities.PaymentClientDepositResponse:
        # https://stpmex.zendesk.com/hc/en-us/articles/360053021391-Register-QR-Collection
        assert self.trx.user_data
        assert self.trx.user_data.phone

        unique_id = get_or_create_unique_id(transaction_id=self.trx.id)
        data = self._deposit(
            phone=self.trx.user_data.phone,
            amount=str(self.trx.amount),
            unique_transaction_id=unique_id,
            trx_uuid=str(self.trx.uuid),
            creds=self.creds,
            session=self.session,
            deposit_type="qr",
        )

        return entities.PaymentClientDepositResponse(
            status=entities.TransactionStatus.PENDING,
            id_in_payment_system=str(unique_id),
            raw_response=data,
        )

    def deposit_app(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.user_data
        assert self.trx.user_data.phone

        unique_id = get_or_create_unique_id(transaction_id=self.trx.id)
        data = self._deposit(
            phone=self.trx.user_data.phone,
            amount=str(self.trx.amount),
            unique_transaction_id=unique_id,
            trx_uuid=str(self.trx.uuid),
            creds=self.creds,
            session=self.session,
            deposit_type="app",
        )

        return entities.PaymentClientDepositResponse(
            status=entities.TransactionStatus.PENDING
            if data["estadoPeticion"] == str(self.REMOTE_STATUS_SUCCESS)
            else entities.TransactionStatus.FAILED,
            raw_response=data,
            id_in_payment_system=data.get("folioCodi"),
            decline_code=str(data["estadoPeticion"]),
            decline_reason=STP_CODI_ESTADO_PETICION_CODES_TO_DESCRIPTION[
                int(data["estadoPeticion"])
            ],
        )

    def _make_request(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        # TODO: registraCobroQR for QR
        resp = self.session.post(
            f"{self.creds.base_url}{url}",
            json=payload,
        )
        return resp.json()

    def _get_transaction_status(self) -> RemoteTransactionStatus:
        assert self.trx.id_in_payment_system

        payload = {
            "folioCodi": self.trx.id_in_payment_system,
            "empresa": self.creds.empresa,
        }

        payload["firma"] = self.get_stp_signature(
            columns=["folioCodi", "empresa"],
            private_key=self.creds.private_key.get_secret_value(),
            private_key_password=self.creds.private_key_password.get_secret_value(),
            data=payload,
        )
        result = self._make_request(
            url="/codi/cadenaConsultaEstadoOperacion",
            payload=payload,
        )

        estadoPeticion = int(result["estadoPeticion"])
        if estadoPeticion != 0:
            return RemoteTransactionStatus(
                operation_status=entities.TransactionStatus.FAILED,
                decline_code=str(estadoPeticion),
                decline_reason=STP_CODI_ESTADO_PETICION_CODES_TO_DESCRIPTION[
                    estadoPeticion
                ]
                + " / "
                + result.get("descripcionError", ""),
                raw_data=result,
            )

        estadoCodi = int(result["estadoCodi"])
        if estadoCodi == 1:
            return RemoteTransactionStatus(
                operation_status=entities.TransactionStatus.SUCCESS,
                raw_data=result,
            )

        return RemoteTransactionStatus(
            operation_status=entities.TransactionStatus.PENDING,
            raw_data=result,
        )

    @classmethod
    def get_stp_signature(
        cls,
        data: dict[str, Any],
        columns: list[str],
        private_key: str,
        private_key_password: str,
    ) -> str:
        """
        Creates a signature for STP requests.
        """
        parts: list[str] = []

        for col in columns:
            parts.append(str(data.get(col, "")))

        payload_to_sign = "|".join(parts)
        payload_to_sign = f"||{payload_to_sign}||"

        loaded_key = serialization.load_pem_private_key(
            private_key.encode(),
            password=private_key_password.encode(),
        )
        sign_bytes = loaded_key.sign(payload_to_sign.encode(), padding.PKCS1v15(), hashes.SHA256())  # type: ignore
        signature_b64 = base64.b64encode(sign_bytes)
        sign = signature_b64.decode("utf-8")
        logger.info(
            "signed payload for spei_stp",
            extra={
                "payload": data,
                "payload_to_sign": payload_to_sign,
                "signature": sign,
            },
        )
        return sign


class StpCodiSandboxClient(StpCodiClient, BaseSandboxClientMixin[StpCodiCredentials]):
    def _make_request(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "estadoPeticion": "0",
            "folioCodi": f"sandbox: {uuid4()}",
            "resultado": "sandbox",
        }

    @classmethod
    def _deposit(
        cls,
        *,
        phone: str,
        deposit_type: Literal["app", "qr"],
        amount: str,
        unique_transaction_id: int,
        trx_uuid: str,
        creds: StpCodiCredentials,
        session: requests.Session,
    ) -> dict[str, Any]:
        if deposit_type == "app":
            return {
                "estadoPeticion": "0",
                "folioCodi": f"sandbox: {uuid4()}",
                "resultado": "sandbox",
            }
        elif deposit_type == "qr":
            return {}

        raise RuntimeError

    @classmethod
    def get_stp_signature(
        cls,
        data: dict[str, Any],
        columns: list[str],
        private_key: str,
        private_key_password: str,
    ) -> str:
        return ""


def create_key_pair(password: str) -> tuple[str, str, str]:
    """
    Creates a new private/public key pair for STP.
    """
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)
    private_key = crypto.dump_privatekey(
        crypto.FILETYPE_PEM, key, "aes256", password.encode()
    ).decode()
    public_key = crypto.dump_publickey(crypto.FILETYPE_PEM, key).decode()
    return private_key, public_key, password
