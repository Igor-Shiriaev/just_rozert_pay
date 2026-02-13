import base64
import datetime
import hashlib
import json
import logging
import typing as ty
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pydantic
from bm.datatypes import Money
from django import forms
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from pydantic import BaseModel
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.common.const import PaymentSystemType, TransactionStatus
from rozert_pay.payment import entities, tasks, types
from rozert_pay.payment.api_v1.serializers import DepositTransactionRequestSerializer
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import (
    base_classes,
    db_services,
    deposit_services,
    sandbox_services,
    transaction_actualization,
)
from rozert_pay.payment.services.errors import Error, wrap_errors
from rozert_pay.payment.systems.base_controller import PaymentSystemController

logger = logging.getLogger(__name__)


class PaycashCredentials(BaseModel):
    host: str
    emisor: str  # issuer id
    key: pydantic.SecretStr  # secret key for REST service
    test_mode: bool = False
    redirect_host: str = "http://ec2-3-140-103-165.us-east-2.compute.amazonaws.com:8085"


FETCHA_OPERATION = "fetchaOperation"


class PaycashClient(base_classes.BasePaymentClient[PaycashCredentials]):
    credentials_cls = PaycashCredentials

    def get_auth_token(self) -> str:
        # # TODO: add redis cache
        # if t := cache.get("paycash_auth_token"):
        #     return t
        resp = self.session.get(
            f"{self.creds.host}/v1/authre?key={self.creds.key.get_secret_value()}",
        )
        resp.raise_for_status()

        token = resp.json()["Authorization"]
        cache.set("paycash_auth_token", token, timeout=600)
        return token

    def generate_reference(
        self,
        *,
        amount: Decimal,
        trx_id: str,
    ) -> entities.PaymentClientDepositResponse:
        expiration_date = (timezone.now() + timedelta(days=1)).date()

        token = self.get_auth_token()

        resp = self.session.post(
            f"{self.creds.host}/v1/reference",
            json={
                "Amount": str(amount),
                "ExpirationDate": expiration_date.strftime("%Y-%m-%d"),
                "Value": str(trx_id),
                "Type": True,
            },
            headers={
                "Authorization": token,
            },
        )

        resp.raise_for_status()
        response_json = resp.json()

        if "ErrorCode" in response_json and response_json["ErrorCode"] != "0":
            return entities.PaymentClientDepositResponse(
                status=TransactionStatus.FAILED,
                raw_response=response_json,
                decline_code=response_json["ErrorCode"],
                decline_reason=response_json["ErrorMessage"],
            )

        return entities.PaymentClientDepositResponse(
            status=TransactionStatus.PENDING,
            raw_response=response_json,
            id_in_payment_system=response_json["Reference"],
        )

    def _get_transaction_status(self) -> RemoteTransactionStatus:
        fetcha_operation = self.trx.extra.get(FETCHA_OPERATION)
        assert (
            fetcha_operation
        ), "fetchaOperation is missing, cannot get transaction status"
        return self.get_transaction_status_for_date(fetcha_operation)

    def get_transaction_status_for_date(
        self, fetcha_operation: str
    ) -> RemoteTransactionStatus:
        token = self.get_auth_token()
        assert self.trx.id_in_payment_system

        resp = self.session.get(
            # 02/12/2024
            f"{self.creds.host}/v1/payments?Date={fetcha_operation}",
            headers={
                "Authorization": token,
            },
        )
        resp.raise_for_status()

        parsed = resp.json()
        for payment in parsed[0]["Payments"]:
            if payment["Reference"] == self.trx.id_in_payment_system:
                return RemoteTransactionStatus(
                    operation_status={
                        0: TransactionStatus.SUCCESS,
                        1: TransactionStatus.SUCCESS,
                    }.get(int(payment["Status"]), TransactionStatus.PENDING),
                    raw_data=payment,
                    transaction_id=self.trx.id,
                    remote_amount=Money(payment["Amount"], currency="MXN"),
                )

        return RemoteTransactionStatus(
            operation_status=TransactionStatus.PENDING,
            raw_data={"__original_response__": parsed},
            transaction_id=self.trx.id,
        )


class SandboxPaycashClient(
    PaycashClient, base_classes.BaseSandboxClientMixin[PaycashCredentials]
):
    def get_auth_token(self) -> str:
        return "fake"

    def generate_reference(
        self, *, amount: Decimal, trx_id: str
    ) -> entities.PaymentClientDepositResponse:
        return entities.PaymentClientDepositResponse(
            status=const.TransactionStatus.PENDING,
            raw_response={"Reference": "fake"},
            id_in_payment_system=sandbox_services.get_random_id(
                PaymentSystemType.PAYCASH
            ),
        )


class PayCashController(PaymentSystemController[PaycashClient, SandboxPaycashClient]):
    client_cls = PaycashClient
    sandbox_client_cls = SandboxPaycashClient

    def _run_deposit(
        self, trx_id: types.TransactionId, client: PaycashClient | SandboxPaycashClient
    ) -> None:
        trx = db_services.get_transaction(trx_id=trx_id, for_update=False)
        creds = client.creds

        assert trx.currency == "MXN"
        response = client.generate_reference(
            amount=trx.amount,
            trx_id=str(trx.uuid),
        )

        with transaction.atomic():
            trx = db_services.get_transaction(trx_id=trx_id, for_update=True)

            if response.status == const.TransactionStatus.FAILED:
                assert response.decline_code
                return self.fail_transaction(
                    trx,
                    decline_code=response.decline_code,
                    decline_reason=response.decline_reason,
                )

            assert response.id_in_payment_system
            trx.id_in_payment_system = response.id_in_payment_system

            emisor_secret = creds.emisor
            emisor_sha = (
                hashlib.sha1(emisor_secret.encode()).hexdigest().encode().upper()
            )
            emisor_b64 = base64.b64encode(emisor_sha).decode()
            # key_secret = client.get_auth_token()
            key_secret = creds.key.get_secret_value()
            key_sha = hashlib.sha1(key_secret.encode()).hexdigest().encode().upper()
            key_b64 = base64.b64encode(key_sha).decode()
            reference_b64 = base64.b64encode(
                response.id_in_payment_system.encode()
            ).decode()

            # print(
            #     f"""
            # Original:
            # Emisor: {emisor_secret}
            # Key: {key_secret}
            # Reference: {reference}
            #
            # SHA1:
            # Emisor: {emisor_sha}
            # Key: {key_sha}
            #
            # Base64:
            # Emisor: {emisor_b64}
            # Key: {key_b64}
            # Reference: {reference_b64}
            # """
            # )
            deposit_services.create_deposit_instruction(
                trx=trx,
                type=const.InstructionType.INSTRUCTION_FILE,
                link=f"{creds.redirect_host}/formato.php?"
                f"emisor={emisor_b64}&"
                f"token={key_b64}&"
                f"referencia={reference_b64}"
                + (creds.test_mode and "&interno=1" or ""),
                save=False,
            )
            trx.save()

            self.create_callback(
                trx_id=trx_id,
                callback_type=const.CallbackType.TRANSACTION_UPDATED,
            )

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        body = json.loads(cb.body)
        with transaction.atomic():
            trx = db_services.get_transaction(
                for_update=True,
                id_in_payment_system=body["payment"]["Referencia"],
                system_type=const.PaymentSystemType.PAYCASH,
            )
            fecha_operation = datetime.datetime.fromisoformat(
                body["payment"]["FechaConfirmation"]
            ).strftime("%Y-%m-%d")
            trx.extra[FETCHA_OPERATION] = fecha_operation
            trx.save_extra()

            transaction.on_commit(lambda: tasks.check_status.delay(trx.id))

        return RemoteTransactionStatus.initial(
            raw_data=body,
            transaction_id=trx.id,
            id_in_payment_system=trx.id_in_payment_system,
        )

    def build_callback_response(self, cb: IncomingCallback) -> Response:
        if cb.error_type:
            return Response(
                {
                    "code": 400,
                    "message": cb.error_type,
                }
            )
        return Response(
            {
                "code": 200,
                "message": "payment successfully notified",
            }
        )

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        return True


class PaycashActualizationForm(transaction_actualization.TransactionActualizationForm):
    fetchaOperation = forms.DateField(
        help_text=(
            "Please specify the operation date on the Paycash side. IMPORTANT! "
            "If the date is incorrect, the actualization method will not be able to find "
            "the transaction and will return the PENDING status, "
            "even if the transaction has already been processed."
        ),
        input_formats=["%Y-%m-%d"],
    )

    def __init__(self, trx: PaymentTransaction, data: dict[str, ty.Any] | None = None):
        super().__init__(trx, data)

        if trx.extra and data and (fo := trx.extra.get(FETCHA_OPERATION)):
            data[FETCHA_OPERATION] = fo

        if data and not data.get(FETCHA_OPERATION):
            self.fields[FETCHA_OPERATION].required = True
            self.fields.pop("actualize")

        if data and not data.get(FETCHA_OPERATION):
            data[FETCHA_OPERATION] = trx.extra.get(
                FETCHA_OPERATION
            ) or trx.updated_at.date().strftime("%Y-%m-%d")


class PaycashActualizer(
    transaction_actualization.BaseTransactionActualizer[PaycashActualizationForm]
):
    form_cls = PaycashActualizationForm

    @wrap_errors
    def get_remote_status(
        self,
        transaction: PaymentTransaction,
        data: dict[str, ty.Any],
    ) -> Error | entities.RemoteTransactionStatus:
        return paycash_controller.get_client(
            transaction
        ).get_transaction_status_for_date(data[FETCHA_OPERATION])

    def get_form(self, data: dict[str, Any]) -> PaycashActualizationForm | Error:
        if not data.get(FETCHA_OPERATION):
            return PaycashActualizationForm(self.transaction, data)
        return super().get_form(data)


@extend_schema(
    tags=["Paycash"],
)
class PaycashViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[Any],
):
    @extend_schema(
        operation_id="Create Paycash deposit transaction",
        request=DepositTransactionRequestSerializer,
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data, serializer_class=DepositTransactionRequestSerializer
        )


paycash_controller: PayCashController = PayCashController(
    payment_system=const.PaymentSystemType.PAYCASH,
    default_credentials={
        "host": "fake",
        "emisor": "fake",
        "key": "fake",
        "test_mode": True,
    },
    transaction_actualizer_cls=PaycashActualizer,
)
