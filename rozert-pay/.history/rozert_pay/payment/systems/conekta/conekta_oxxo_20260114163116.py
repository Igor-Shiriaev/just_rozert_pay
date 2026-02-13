import base64
import datetime
import json
import logging
import re
from decimal import Decimal
from typing import Any, Callable, Literal, Optional
from uuid import UUID

import requests
from bm.datatypes import Money
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from currency.utils import from_minor_units, to_minor_units
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from pydantic import BaseModel, SecretStr
from requests import Session
from rest_framework import serializers as drf_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.common.helpers.log_utils import LogWriter
from rozert_pay.payment import entities, tasks
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, Wallet
from rozert_pay.payment.services import (
    base_classes,
    db_services,
    deposit_services,
    sandbox_services,
    transaction_processing,
    wallets_management,
)
from rozert_pay.payment.services.errors import Error
from rozert_pay.payment.systems.base_controller import PaymentSystemController
from rozert_pay.payment.systems.conekta.constants import (
    IGNORED_CALLBACK_EVENTS,
    PAYMENT_STATUSES_MAPPING,
    PROCESSING_CALLBACK_EVENTS,
)

logger = logging.getLogger(__name__)


class ConektaOxxoCredentials(BaseModel):
    api_token: SecretStr
    webhook_public_key: SecretStr
    base_url: str


class ConektaOxxoClient(base_classes.BasePaymentClient[ConektaOxxoCredentials]):
    credentials_cls = ConektaOxxoCredentials

    @classmethod
    def get_auth_token_cls(cls, creds: ConektaOxxoCredentials) -> str:
        return f"Bearer {creds.api_token.get_secret_value()}"

    @classmethod
    def make_request_cls(
        cls,
        *,
        session: Session,
        creds: ConektaOxxoCredentials,
        path: str,
        method: Literal["get", "post", "delete"],
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = f"{creds.base_url}{path}"
        token = cls.get_auth_token_cls(creds)
        headers = {
            "Authorization": token,
            "Accept": "application/vnd.conekta-v2.1.0+json",
        }

        response: requests.Response = getattr(session, method)(
            url=url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    @classmethod
    def _update_webhook_public_key(
        cls, wallet: Wallet, creds: ConektaOxxoCredentials
    ) -> None:
        response_with_public_key = cls.make_request_cls(
            session=requests.Session(),
            creds=creds,
            path="/webhook_keys/",
            method="get",
        )
        active_keys = [
            key_entity["public_key"]
            for key_entity in response_with_public_key["data"]
            if key_entity["active"] is True
        ]
        if len(active_keys) != 1:
            raise ValueError(f"Expected 1 active key, got {len(active_keys)}")

        wallet.credentials.update({"webhook_public_key": active_keys[0]})
        wallet.save()

    def deposit(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.user_data
        assert self.trx.user_data.email
        assert self.trx.user_data.phone
        assert self.trx.user_data.first_name
        assert self.trx.user_data.last_name

        payload = {
            "currency": self.trx.currency,
            "customer_info": {
                "email": self.trx.user_data.email,
                "phone": self.trx.user_data.phone,
                "name": f"{self.trx.user_data.first_name} {self.trx.user_data.last_name}",
            },
            "line_items": [
                {
                    "name": "Balance recharge",
                    "unit_price": int(
                        to_minor_units(
                            self.trx.amount,
                            self.trx.currency,
                        )
                    ),
                    "quantity": 1,
                }
            ],
            "metadata": {
                "transaction_uuid": str(self.trx.uuid),
            },
            "charges": [
                {
                    "payment_method": {
                        "type": "oxxo_cash",
                        "expires_at": int(
                            (timezone.now() + datetime.timedelta(hours=24)).timestamp()
                        ),
                    }
                },
            ],
        }

        response = self._make_request(
            path="/orders/",
            method="post",
            payload=payload,
        )
        if response["object"] == "error":
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=response,
                decline_code=response["type"],
                decline_reason=str(response["details"]),
            )

        return entities.PaymentClientDepositResponse(
            status=entities.TransactionStatus.PENDING,
            raw_response=response,
            id_in_payment_system=response["id"],
        )

    def _make_request(
        self,
        path: str,
        method: Literal["get", "post", "delete"],
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return self.make_request_cls(
            session=self.session,
            creds=self.creds,
            path=path,
            method=method,
            payload=payload,
        )

    def _get_transaction_status(self) -> entities.RemoteTransactionStatus:
        response = self._make_request(
            path=f"/orders/{self.trx.id_in_payment_system}",
            method="get",
        )
        if response["object"] == "error":
            if response["type"] == "resource_not_found_error":
                return entities.RemoteTransactionStatus(
                    operation_status=const.TransactionStatus.FAILED,  # NOT FOUND ??????
                    raw_data=response,
                    decline_code=response["type"],
                    decline_reason=str(response["details"]),
                    transaction_id=self.trx.id,
                )
            else:
                raise ValueError(f'Unknown error type: {response["type"]} {response!r}')

        operation_status = PAYMENT_STATUSES_MAPPING[response["payment_status"]]
        decline_code: str | None = None
        if operation_status == const.TransactionStatus.FAILED:
            decline_code = response["payment_status"]

        return entities.RemoteTransactionStatus(
            operation_status=operation_status,
            raw_data=response,
            id_in_payment_system=response["id"],
            decline_code=decline_code,
            remote_amount=Money(
                value=from_minor_units(
                    Decimal(response["amount"]), response["currency"]
                ),
                currency=response["currency"],
            ),
        )

    @classmethod
    def _remove_webhook(cls, webhook_id: str, creds: ConektaOxxoCredentials) -> None:
        cls.make_request_cls(
            session=requests.Session(),
            creds=creds,
            path=f"/webhooks/{webhook_id}",
            method="delete",
        )

    @classmethod
    def _create_webhook(
        cls,
        url: str,
        creds: ConektaOxxoCredentials,
    ) -> entities.Webhook | None:
        response = cls.make_request_cls(
            path="/webhooks/",
            method="post",
            payload={
                "url": url,
                "synchronous": "false",
            },
            session=requests.Session(),
            creds=creds,
        )
        return entities.Webhook(
            id=response["id"],
            url=response["url"],
            raw_data=response,
        )

    @classmethod
    def get_webhooks(cls, creds: ConektaOxxoCredentials) -> list[entities.Webhook]:
        result = cls.make_request_cls(
            path="/webhooks/",
            method="get",
            session=requests.Session(),
            creds=creds,
            payload=None,
        )
        assert not result["has_more"]

        return [
            entities.Webhook(
                id=webhook["id"],
                url=webhook["url"],
                raw_data=webhook,
            )
            for webhook in result["data"]
        ]

    @classmethod
    def setup_webhooks(
        cls,
        *,
        creds: T_Credentials,
        logger: LogWriter,
        wallet: Wallet | None = None,
        system: PaymentSystem | None = None,
        url: str | None = None,
        only_clear_existing: bool = False,
        remove_existing: bool = False,
        remove_pattern: re.Pattern[str] = re.compile(".*rozert.cloud.*"),
        only_rozert_urls: bool = True,
    ) -> None:
        super().setup_webhooks(
            creds=creds,
            logger=logger,
            wallet=wallet,
            url=url,
            only_clear_existing=only_clear_existing,
            remove_existing=remove_existing,
            remove_pattern=remove_pattern,
        )

        if not only_clear_existing:
            cls._update_webhook_public_key(wallet, creds)


class SandboxConektaOxxoClient(
    ConektaOxxoClient, base_classes.BaseSandboxClientMixin[ConektaOxxoCredentials]
):
    @classmethod
    def get_auth_token_cls(cls, _: ConektaOxxoCredentials) -> str:
        return "fake"

    @classmethod
    def make_request_cls(
        cls,
        *,
        session: Session,
        creds: ConektaOxxoCredentials,
        path: str,
        method: Literal["get", "post", "delete"],
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        match path:
            case "/orders/":
                return {
                    "id": "ord_123",
                    "object": "order",
                    "amount": 10000,
                    "currency": "MXN",
                    "payment_status": "pending",
                    "charges": [
                        {
                            "payment_method": {
                                "type": "oxxo_cash",
                                "reference": sandbox_services.get_random_id(
                                    const.PaymentSystemType.CONEKTA_OXXO
                                ),
                            },
                        },
                    ],
                }
            case _:  # pragma: no cover
                raise RuntimeError


class ConektaOxxoController(
    PaymentSystemController[ConektaOxxoClient, SandboxConektaOxxoClient]
):
    client_cls = ConektaOxxoClient
    sandbox_client_cls = SandboxConektaOxxoClient

    def _run_deposit(
        self, trx_id: int, client: ConektaOxxoClient | SandboxConektaOxxoClient
    ) -> None:
        response: entities.PaymentClientDepositResponse = client.deposit()
        with transaction.atomic():
            locked_trx = db_services.get_transaction(trx_id=trx_id, for_update=True)

            if response.status == const.TransactionStatus.FAILED:
                assert response.decline_code
                return self.fail_transaction(
                    locked_trx,
                    decline_code=response.decline_code,
                    decline_reason=response.decline_reason,
                )

            locked_trx.id_in_payment_system = response.id_in_payment_system
            locked_trx.save()

            try:
                reference = response.raw_response["charges"]["data"][0][
                    "payment_method"
                ]["reference"]
            except Exception:
                reference = None

            if reference:
                deposit_services.create_deposit_instruction(
                    trx=locked_trx,
                    type=const.InstructionType.INSTRUCTION_REFERENCE,
                    reference=reference,
                )

            transaction_processing.schedule_periodic_status_checks(
                trx=locked_trx,
            )

    def _parse_callback(
        self, cb: IncomingCallback
    ) -> RemoteTransactionStatus | Response:
        body = json.loads(cb.body)
        callback_type = body["type"]
        id_in_payment_system = body["data"]["object"].get("order_id")
        if id_in_payment_system is None:
            trx_uuid = body["data"]["object"]["metadata"]["transaction_uuid"]
            trx = db_services.get_transaction(
                for_update=False,
                trx_uuid=UUID(trx_uuid),
                system_type=const.PaymentSystemType.CONEKTA_OXXO,
            )
        else:
            trx = db_services.get_transaction(
                for_update=False,
                id_in_payment_system=str(id_in_payment_system),
                system_type=const.PaymentSystemType.CONEKTA_OXXO,
            )

        if callback_type in IGNORED_CALLBACK_EVENTS:
            logger.info(
                "Skip callback because its type is ignored",
                extra={
                    "callback_type": callback_type,
                    "callback_payload": body,
                },
            )
            return Response("")

        assert callback_type in PROCESSING_CALLBACK_EVENTS

        client = self.get_client(trx)
        _validate_conekta_webhook_signature(creds=client.creds, callback=cb)

        tasks.check_status.delay(trx.id)
        return RemoteTransactionStatus.initial(
            raw_data={},
            transaction_id=trx.id,
        )

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        # We do not explicitly check the callback signature here because the signature is verified
        # during the callback parsing process in `_parse_callback`.
        return True

    def _get_action_on_credentials_change(
        self,
    ) -> (
        Callable[
            [Wallet, dict[str, Any], dict[str, Any], LogWriter],
            None | Error,
        ]
        | None
    ):
        return wallets_management.setup_webhooks_credentials_change_action(
            client_cls=ConektaOxxoClient,
        )


def _validate_conekta_webhook_signature(
    creds: ConektaOxxoCredentials, callback: IncomingCallback
) -> None:
    digest: str | None = callback.headers.get("digest")
    if digest is None:
        raise ValidationError("Missing DIGEST header in Conekta webhook")

    signature = base64.b64decode(digest)
    public_key = load_pem_public_key(
        creds.webhook_public_key.get_secret_value().encode()
    )
    assert isinstance(public_key, RSAPublicKey), "Expected RSA public key"

    message = callback.body.encode("utf-8")
    try:
        public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise ValidationError("Invalid Conekta webhook signature")


conekta_oxxo_controller = ConektaOxxoController(
    payment_system=const.PaymentSystemType.CONEKTA_OXXO,
    default_credentials={
        "api_token": "fake",
        "webhook_public_key": "fake",
        "base_url": "https://fake.com",
    },
)


class ConektaOxxoDepositSerializer(
    serializers.DepositTransactionRequestSerializer,
    serializers.user_data_serializer_mixin_factory(  # type: ignore[misc]
        "ConektaOxxoUserData",
        required_fields=["email", "phone", "first_name", "last_name"],
    ),
):
    redirect_url = drf_serializers.URLField(required=True)


@extend_schema(
    tags=["Conekta OXXO"],
)
class ConektaOxxoViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[Any],
):
    @extend_schema(
        operation_id="Create Conekta OXXO deposit transaction",
        request=ConektaOxxoDepositSerializer,
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data, serializer_class=ConektaOxxoDepositSerializer
        )
