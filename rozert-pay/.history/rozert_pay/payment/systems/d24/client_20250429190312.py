import base64
import logging
from typing import Any
from uuid import uuid4

from OpenSSL import crypto
from rozert_pay.payment import entities
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.services.base_classes import (
    BasePaymentClient,
    BaseSandboxClientMixin,
)
from rozert_pay.payment.systems.stp_codi.entities import StpCodiCredentials

logger = logging.getLogger(__name__)


class D24Client(BasePaymentClient[StpCodiCredentials]):
    credentials_cls = StpCodiCredentials

    REMOTE_STATUS_SUCCESS = 0

    def deposit_qr_code(self) -> entities.PaymentClientDepositResponse:
        # https://stpmex.zendesk.com/hc/en-us/articles/360053021391-Register-QR-Collection
        assert self.trx.user_data

        payload: dict[str, Any] = {
            "registraCobro": {
                "numeroCelularCliente": self.trx.user_data.phone,
                "monto": str(self.trx.amount),
                "cuentaBeneficiario2": self.creds.cuenta_beneficiario2,
                "nombreBeneficiario2": self.creds.nombre_beneficiario2,
                "tipoCuentaBeneficiario2": self.creds.tipo_cuenta_beneficiario2,
                "concepto": f"Order {self.trx.uuid}",
                "empresa": self.creds.empresa,
                "tipoPagoDeSpei": "20",
                "numeroReferenciaComercio": str(self.trx.uuid),
            },
        }
        payload["firma"] = self.get_stp_signature(
            payload["registraCobro"],
            [
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
            ],
            private_key=self.creds.private_key.get_secret_value(),
            private_key_password=self.creds.private_key_password.get_secret_value(),
        )

        data = self._make_request("/codi/registraCobro", payload)

        return entities.PaymentClientDepositResponse(
            status=entities.TransactionStatus.PENDING,
            id_in_payment_system=data["folioCodi"],
            raw_response=data,
        )

    def deposit_app(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.user_data

        # See https://stpmex.zendesk.com/hc/en-us/articles/360060547812-Register-Non-Presential-Collection
        payload: dict[str, Any] = {
            "registraCobro": {
                "numeroCelularCliente": self.trx.user_data.phone,
                "monto": str(self.trx.amount),
                "cuentaBeneficiario2": self.creds.cuenta_beneficiario2,
                "nombreBeneficiario2": self.creds.nombre_beneficiario2,
                "tipoCuentaBeneficiario2": self.creds.tipo_cuenta_beneficiario2,
                "concepto": f"Order {self.trx.uuid}",
                "empresa": self.creds.empresa,
                "tipoPagoDeSpei": "20",
                "numeroReferenciaComercio": str(self.trx.uuid),
            },
        }
        payload["firma"] = self.get_stp_signature(
            payload["registraCobro"],
            [
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
            ],
            private_key=self.creds.private_key.get_secret_value(),
            private_key_password=self.creds.private_key_password.get_secret_value(),
        )

        data = self._make_request("/codi/registraCobro", payload)

        return entities.PaymentClientDepositResponse(
            status=entities.TransactionStatus.PENDING
            if data["estadoPeticion"] == self.REMOTE_STATUS_SUCCESS
            else entities.TransactionStatus.FAILED,
            raw_response=data,
            id_in_payment_system=data.get("folioCodi"),
            decline_code=str(data["estadoPeticion"]),
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
        return RemoteTransactionStatus(
            operation_status={
                self.REMOTE_STATUS_SUCCESS: entities.TransactionStatus.SUCCESS,
            }.get(result["estadoPeticion"], entities.TransactionStatus.FAILED),
            decline_code=str(result["estadoPeticion"]),
            decline_reason=result.get("descripcionError"),
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

        loaded_key = crypto.load_privatekey(
            crypto.FILETYPE_PEM,
            private_key.encode(),
            private_key_password.encode(),
        )
        sign_bytes = crypto.sign(loaded_key, payload_to_sign, "sha256")
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
            "estadoPeticion": 0,
            "folioCodi": f"sandbox: {uuid4()}",
            "resultado": "sandbox",
        }

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
