import hashlib
import hmac
import json
import typing as ty
from urllib.parse import urlencode
from uuid import UUID

import requests
from bm.datatypes import Money
from django.utils import timezone
from pydantic import BaseModel, SecretStr
from requests import Response
from rozert_pay.common import const
from rozert_pay.payment import entities, models, types
from rozert_pay.payment.services import base_classes, errors
from rozert_pay.payment.systems.base_controller import PaymentSystemController
from rozert_pay.payment.systems.bitso_spei.bitso_spei_const import (
    BITSO_SPEI_IS_PAYOUT_REFUNDED,
    BITSO_SPEI_PAYOUT_REFUND_DATA,
    DECLINE_REASON_FAILED,
)
from rozert_pay.payment.systems.bitso_spei.models import BitsoTransactionExtraData


class BitsoSpeiCreds(BaseModel):
    base_api_url: str
    api_key: str
    api_secret: SecretStr


class BitsoSpeiClient(base_classes.BasePaymentClient[BitsoSpeiCreds]):
    payment_system_name = const.PaymentSystemType.BITSO_SPEI
    credentials_cls = BitsoSpeiCreds
    _operation_status_by_foreign_status = {
        "pending": const.TransactionStatus.PENDING,
        "processing": const.TransactionStatus.PENDING,
        "complete": const.TransactionStatus.SUCCESS,
        "failed": const.TransactionStatus.FAILED,
    }

    @classmethod
    def create_deposit_instruction(
        cls,
        *,
        external_customer_id: types.ExternalCustomerId,
        wallet: models.Wallet,
        creds: types.T_Credentials,
    ) -> str | errors.Error:
        bitso_creds = ty.cast(BitsoSpeiCreds, creds)
        resp = cls._make_response(
            method="post", url_path="/spei/v1/clabes", creds=bitso_creds
        )
        if not resp["success"]:
            return errors.Error(
                f"Failed to create deposit instruction: {resp['code']} {resp['message']}"
            )

        return resp["payload"]["clabe"]

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        user_data = self.trx.user_data
        assert user_data

        if self.trx.customer_external_account:
            clabe = self.trx.customer_external_account.unique_account_number
        elif self.trx.withdraw_to_account:
            clabe = self.trx.withdraw_to_account
        else:
            raise RuntimeError(
                "No customer external account or withdraw to account found"
            )

        is_debit_card = len(clabe) == 16

        payload = {
            "currency": self.trx.currency.lower(),
            "protocol": "debitcard" if is_debit_card else "clabe",
            "amount": str(self.trx.amount),
            "numeric_ref": str(self.trx.id)[:7],
            "notes_ref": str(self.trx.uuid),
            "clabe": clabe,
            "beneficiary": user_data.full_name,
            "origin_id": self._prepare_withdrawal_id(self.trx.uuid),
        }

        if is_debit_card:
            # TODO:
            payload["name"] = "Debit card"
            payload["method_name"] = "Debit card"

            card_bin = clabe[:6]
            bitso_bank = BitsoSpeiCardBank.objects.filter(
                is_active=True,
                banks__bin=card_bin,
            ).first()

            if bitso_bank:
                payload["institution_code"] = bitso_bank.code
            else:
                self.log.error(
                    "No BitsoSpeiCardBank found for bin",
                    extra={
                        "clabe": clabe,
                        "card_bin": card_bin,
                        "transaction_uuid": str(trx.uuid),
                    },
                )
                raise ValueError("No BitsoSpeiCardBank found for debit card withdraw")

            bitso_bank = 123

            if bitso_bank:
                payload["institution_code"] = bitso_bank.code
            else:
                PaymentSystemController.create_log(
                    trx_id=self.trx.id,
                    event_type=const.EventType.ERROR,
                    description="No BitsoSpeiCardBank found for bin",
                    extra={
                        "clabe": clabe,
                        "card_bin": card_bin,
                        "transaction_uuid": str(self.trx.uuid),
                    },
                )
                return entities.PaymentClientWithdrawResponse(
                    status=const.TransactionStatus.FAILED,
                    decline_code=const.TransactionDeclineCodes.NO_OPERATION_PERFORMED,
                    decline_reason="No BitsoSpeiCardBank found for debit card withdraw",
                    raw_response={},
                    id_in_payment_system=None,
                )

        resp = self._make_response(
            method="post",
            url_path="/api/v3/withdrawals",
            json_payload=payload,
            creds=self.creds,
        )
        if not resp["success"]:
            return entities.PaymentClientWithdrawResponse(
                status=const.TransactionStatus.FAILED,
                raw_response=resp,
                decline_code=resp["error"]["code"],
                decline_reason=resp["error"]["message"],
                id_in_payment_system=None,
            )

        return entities.PaymentClientWithdrawResponse(
            status=const.TransactionStatus.PENDING,
            raw_response=resp,
            id_in_payment_system=resp["payload"]["wid"],
        )

    @classmethod
    def _make_response(
        cls,
        *,
        method: ty.Literal["get", "post"],
        url_path: str,
        creds: BitsoSpeiCreds,
        json_payload: dict[str, ty.Any] | None = None,
        query_params: dict[str, ty.Any] | None = None,
        log: bool = True,
    ) -> dict[str, ty.Any]:
        nonce = str(int(timezone.now().timestamp() * 1000000))
        headers: dict[str, ty.Any] = {}
        query_str = ""
        payload_str = ""

        if query_params:
            query_str = f"?{urlencode(query_params)}"
        if json_payload:
            headers["Content-Type"] = "application/json"
            payload_str = json.dumps(json_payload)

        sig = hmac.new(
            creds.api_secret.get_secret_value().encode(),
            f"{nonce}{method.upper()}{url_path}{query_str}{payload_str}".encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()
        headers["Authorization"] = f"Bitso {creds.api_key}:{nonce}:{sig}"

        resp: Response = getattr(requests.Session(), method)(
            f"{creds.base_api_url}{url_path}{query_str}",
            data=payload_str or None,
            headers=headers,
        )
        # TODO: response logging. To transaction log?
        # if log:
        #     self.log_and_check_response(resp, ignore_statuses=[400])
        return resp.json()

    def _prepare_withdrawal_id(self, trx_uuid: UUID) -> str:
        return str(trx_uuid).replace("-", "_")

    def _get_transaction_status(self) -> entities.RemoteTransactionStatus:
        if self.trx.type == const.TransactionType.WITHDRAWAL and self.trx.extra.get(
            BITSO_SPEI_IS_PAYOUT_REFUNDED
        ):
            return entities.RemoteTransactionStatus(
                operation_status=const.TransactionStatus.FAILED,
                raw_data={
                    "__note__": "This is not real response. Payout was refunded via "
                    f"deposit, you can find deposit data in {BITSO_SPEI_PAYOUT_REFUND_DATA} field."
                },
                decline_code=const.TransactionDeclineCodes.NO_OPERATION_PERFORMED,
                decline_reason="Payout refunded",
            )

        clave_rastreo_key: str
        if self.trx.type == const.TransactionType.DEPOSIT:
            clave_rastreo_key = "clave_rastreo"
            resp = self._make_response(
                method="get",
                url_path=f"/api/v3/fundings/{self.trx.id_in_payment_system}",
                creds=self.creds,
            )
        elif self.trx.type == const.TransactionType.WITHDRAWAL:
            clave_rastreo_key = "clave_de_rastreo"
            resp = self._make_response(
                method="get",
                url_path="/api/v3/withdrawals",
                query_params={"origin_ids": self._prepare_withdrawal_id(self.trx.uuid)},
                creds=self.creds,
            )
        else:  # pragma: no cover
            raise ValueError(f"Unexpected transaction type {self.trx.type}")

        payload = resp["payload"][0]
        details = payload["details"]
        decline_reason = details.get("fail_reason")
        if decline_reason:  # pragma: no cover
            assert payload["status"] == "failed"
            status = const.TransactionStatus.FAILED
        else:
            status = self._operation_status_by_foreign_status[payload["status"]]
        if (
            status == const.TransactionStatus.FAILED and decline_reason is None
        ):  # pragma: no cover
            decline_reason = DECLINE_REASON_FAILED

        BitsoTransactionExtraData.objects.get_or_create(
            transaction=self.trx,
            clave_rastreo=details[clave_rastreo_key],
        )

        return entities.RemoteTransactionStatus(
            operation_status=status,
            raw_data=resp,
            decline_code=decline_reason,
            decline_reason=decline_reason,
            remote_amount=Money(payload["amount"], str(payload["currency"]).upper()),
            transaction_id=self.trx_id,
        )
