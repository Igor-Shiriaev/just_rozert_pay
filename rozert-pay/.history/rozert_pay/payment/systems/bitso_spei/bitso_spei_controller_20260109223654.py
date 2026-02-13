import base64
import binascii
import json
import logging
import re
from decimal import Decimal
from functools import lru_cache
from typing import Any, Callable

from bm.datatypes import Money
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from django.db import transaction
from pydantic import BaseModel
from rozert_pay.common import const
from rozert_pay.common.const import PaymentSystemType, TransactionStatus
from rozert_pay.common.helpers.log_utils import LogWriter
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction, Wallet
from rozert_pay.payment.services import errors, withdraw_services
from rozert_pay.payment.services.db_services import get_transaction
from rozert_pay.payment.services.errors import Error
from rozert_pay.payment.services.transactions_created_on_callback import (
    process_transaction_creation_on_callback,
)
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.bitso_spei.bitso_services import (
    get_payout_transaction_by_clave_rastreo,
)
from rozert_pay.payment.systems.bitso_spei.bitso_spei_client_sandbox import (
    BitsoSpeiClientSandbox,
)
from rozert_pay.payment.systems.bitso_spei.bitso_spei_const import (
    BITSO_CLAVE_RASTREO_FIELD,
    BITSO_SPEI_IS_PAYOUT_REFUNDED,
    BITSO_SPEI_PAYOUT_REFUND_DATA,
    DECLINE_REASON_FAILED,
)
from rozert_pay.payment.systems.bitso_spei.client import BitsoSpeiClient, BitsoSpeiCreds

logger = logging.getLogger(__name__)


class BitsoSpeiCallbackDetails(BaseModel):
    receive_clabe: str | None = None
    deposit_type: str | None = None
    clave_rastreo: str | None = None
    clave_de_rastreo: str | None = None
    concepto: str | None = None
    sender_clabe: str | None = None
    fail_reason: str | None = None

    class Config:
        extra = "allow"


class BitsoSpeiCallbackPayload(BaseModel):
    amount: Decimal
    currency: str
    status: str
    fid: str | None = None
    details: BitsoSpeiCallbackDetails
    wid: str | None = None

    class Config:
        extra = "allow"


class BitsoSpeiCallbackData(BaseModel):
    raw_data: dict[str, Any]
    event_type: str
    payload: BitsoSpeiCallbackPayload

    @property
    def details(self) -> BitsoSpeiCallbackDetails:
        return self.payload.details

    class Config:
        extra = "allow"


class BitsoSpeiController(
    base_controller.PaymentSystemController[BitsoSpeiClient, BitsoSpeiClientSandbox]
):
    sandbox_client_cls = BitsoSpeiClientSandbox
    client_cls = BitsoSpeiClient
    _operation_status_by_foreign_status = {
        "pending": TransactionStatus.PENDING,
        "processing": TransactionStatus.PENDING,
        "complete": TransactionStatus.SUCCESS,
        "failed": TransactionStatus.FAILED,
        "COMPLETE": TransactionStatus.SUCCESS,
        "FAILED": TransactionStatus.FAILED,
        "PENDING": TransactionStatus.PENDING,
        "PROCESSING": TransactionStatus.PENDING,
    }

    def _run_withdraw(
        self, trx: PaymentTransaction, client: BitsoSpeiClientSandbox | BitsoSpeiClient
    ) -> None:
        with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
            trx=trx,
            controller=self,
        ):
            pass

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        data = json.loads(cb.body)
        payload = data["payload"]

        callback_data = BitsoSpeiCallbackData(
            raw_data=data,
            event_type=data["event"],
            payload=payload,
        )

        return self.callback_logic(
            callback_data=callback_data,
        )

    @classmethod
    def callback_logic(
        cls,
        *,
        callback_data: BitsoSpeiCallbackData,
    ) -> RemoteTransactionStatus:
        payload = callback_data.payload
        details = callback_data.details

        if callback_data.event_type == "funding":  # deposit
            receive_clabe = details.receive_clabe

            if (
                details.deposit_type == "FAIL_WITHDRAWAL_COMPENSATION"
            ):  # Withdrawal refund
                assert (
                    details.clave_rastreo
                ), "clave_rastreo is required for withdrawal refunds"
                with transaction.atomic():
                    trx: PaymentTransaction = get_payout_transaction_by_clave_rastreo(
                        clave_rastreo=details.clave_rastreo,
                        amount=payload.amount,
                    )
                    trx.extra[BITSO_SPEI_IS_PAYOUT_REFUNDED] = True
                    trx.extra[BITSO_SPEI_PAYOUT_REFUND_DATA] = callback_data.raw_data
                    trx.save()

                return RemoteTransactionStatus(
                    operation_status=TransactionStatus.FAILED,
                    raw_data=callback_data.raw_data,
                    transaction_id=trx.id,
                    decline_code=details.deposit_type,
                    decline_reason=details.concepto,
                    remote_amount=Money(payload.amount, payload.currency.upper()),
                )

            elif receive_clabe:
                wallet_identity = details.sender_clabe
                assert wallet_identity, "sender_clabe is required for deposits"

                id_in_payment_system = payload.fid
                assert id_in_payment_system

                clave_rastreo = details.clave_rastreo
                assert clave_rastreo, "clave_rastreo is required for deposits"
                with process_transaction_creation_on_callback(
                    deposit_instruction_account_number=receive_clabe,
                    deposited_from_account_number=wallet_identity,
                    system_type=PaymentSystemType.BITSO_SPEI,
                    controller=bitso_spei_controller,
                    amount=Money(payload.amount, payload.currency.upper()),
                    id_in_payment_system=id_in_payment_system,
                    transaction_extra={
                        BITSO_CLAVE_RASTREO_FIELD: clave_rastreo,
                    },
                ) as trx_or_err:
                    assert isinstance(trx_or_err, PaymentTransaction)
                    trx = trx_or_err
            else:
                raise RuntimeError
        elif callback_data.event_type == "withdrawal":
            id_in_payment_system = payload.wid
            assert id_in_payment_system, "wid is required for withdrawal callbacks"
            with transaction.atomic():
                trx = get_transaction(
                    for_update=True,
                    id_in_payment_system=id_in_payment_system,
                    system_type=PaymentSystemType.BITSO_SPEI,
                )
                trx.extra[BITSO_CLAVE_RASTREO_FIELD] = payload.details.clave_de_rastreo
                trx.save_extra()
        else:
            raise ValueError("Unexpected event")

        decline_reason = details.fail_reason
        if decline_reason:
            operation_status = TransactionStatus.FAILED
        else:
            operation_status = cls._operation_status_by_foreign_status[payload.status]
        if operation_status == TransactionStatus.FAILED and decline_reason is None:
            decline_reason = DECLINE_REASON_FAILED

        if trx.extra.get(BITSO_SPEI_IS_PAYOUT_REFUNDED):
            assert operation_status == TransactionStatus.FAILED
        return RemoteTransactionStatus(
            operation_status=operation_status,
            raw_data=callback_data.raw_data,
            transaction_id=trx.id,
            id_in_payment_system=id_in_payment_system,
            remote_amount=Money(payload.amount, payload.currency.upper()),
            decline_code=decline_reason,
            decline_reason=decline_reason,
        )

    @classmethod
    @lru_cache
    @errors.wrap_errors
    def _get_public_key(cls, key_id: str) -> RSAPublicKey | Error:
        wallets = Wallet.objects.filter(system__type=PaymentSystemType.BITSO_SPEI)
        for wallet in wallets:
            credentials = wallet.credentials
            public_keys = credentials.get("public_keys") or []

            for key_data in public_keys:
                if str(key_data.get("key_id")) != str(key_id):
                    continue

                pem_value = (
                    key_data.get("public_key")
                    or key_data.get("pem")
                    or key_data.get("key")
                    or key_data.get("value")
                )
                if not pem_value:
                    continue

                pem_bytes = pem_value.encode("utf-8")
                public_key = load_pem_public_key(pem_bytes)
                if not isinstance(public_key, RSAPublicKey):
                    return Error("Bitso public key is not RSA")
                return public_key

        return Error(f"Bitso public key with id {key_id!r} not found")

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        signature_header = cb.headers.get("x-bitso-webhook-event-signature")
        key_id_header = cb.headers.get("x-bitso-key-id")

        if not signature_header:
            cb.error = "Bitso signature header is missing"
            return False

        if not key_id_header:
            cb.error = "Bitso key id header is missing"
            return False

        public_key = self._get_public_key(key_id_header)
        if isinstance(public_key, Error):
            cb.error = f"Unable to get public key: {public_key}"
            return False

        try:
            signature_bytes = base64.b64decode(signature_header, validate=True)
        except (binascii.Error, ValueError) as exc:
            cb.error = f"Invalid Bitso signature encoding: {exc}"
            return False

        body_json = json.loads(cb.body)

        payload = body_json.get("payload")
        if payload is None:
            cb.error = "Callback payload is missing"
            return False

        payload_bytes = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")

        try:
            public_key.verify(signature_bytes, payload_bytes, PKCS1v15(), SHA256())
        except InvalidSignature:
            cb.error = "Bitso signature verification failed"
            return False

        return True

    def _get_action_on_credentials_change(
        self,
    ) -> (
        Callable[[Wallet, dict[str, Any], dict[str, Any], LogWriter], None | Error]
        | None
    ):
        @errors.wrap_errors
        def on_creds_change(
            wallet: Wallet,
            old_creds: dict[str, Any],
            new_creds: dict[str, Any],
            lw: LogWriter,
        ) -> None:
            BitsoSpeiClient.remove_webhooks(
                urls_=re.compile(r".*rozert\.cloud.*"),
                creds=BitsoSpeiCreds(**old_creds),
                log_writer=lw,
            )
            BitsoSpeiClient.setup_webhooks(
                creds=BitsoSpeiCreds(**new_creds),
                logger=lw,
                wallet=wallet,
                remove_existing=True,
            )
            wallet.credentials.update(
                dict(
                    public_keys=BitsoSpeiClient.get_public_keys(
                        BitsoSpeiCreds(**new_creds)
                    )
                )
            )
            wallet.save(update_fields=["credentials_encrypted"])
            lw.write("Saved public keys to creds")

        return on_creds_change


bitso_spei_controller = BitsoSpeiController(
    payment_system=PaymentSystemType.BITSO_SPEI,
    default_credentials={
        "base_api_url": "https://bitsospei",
        "api_key": "fake",
        "api_secret": "fake",
    },
    allow_transition_success_to_failed_for=[const.TransactionType.WITHDRAWAL],
)
