import datetime
import json
import logging
import re
import typing as ty
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional
from uuid import uuid4

import requests
from bm.datatypes import Money
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from pydantic import BaseModel, SecretStr
from requests import HTTPError, Session
from requests.auth import HTTPBasicAuth
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.common.const import TransactionExtraFields
from rozert_pay.common.helpers.log_utils import LogWriter
from rozert_pay.payment import entities, tasks
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.payment.entities import (
    RemoteTransactionStatus,
    TransactionExtraFormData,
)
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction, Wallet
from rozert_pay.payment.services import (
    base_classes,
    db_services,
    transaction_processing,
)
from rozert_pay.payment.services.errors import Error
from rozert_pay.payment.services.transaction_status_validation import (
    CleanRemoteTransactionStatus,
)
from rozert_pay.payment.systems.base_controller import PaymentSystemController

if TYPE_CHECKING:
    from rozert_pay.payment.services.db_services import LockedTransaction


logger = logging.getLogger(__name__)


def prepare_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)[-14:]


class PaypalCredentials(BaseModel):
    private_key: SecretStr
    public_key: SecretStr
    base_url: str



class PaypalTransactionExtraFields(TransactionExtraFields):
    PAYPAL_CAPTURE_ID = "paypal_capture_id"
    PAYPAL_ORDER_ID = "paypal_order_id"


class PaypalClient(base_classes.BasePaymentClient[PaypalCredentials]):
    credentials_cls = PaypalCredentials

    @classmethod
    def get_auth_token_cls(self, session: Session, creds: PaypalCredentials) -> str:
        response = session.post(
            f"{creds.base_url}/v1/oauth2/token",
            auth=HTTPBasicAuth(creds.client_id, creds.client_secret.get_secret_value()),
            data={"grant_type": "client_credentials"},
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def get_auth_token(self) -> str:
        return self.get_auth_token_cls(self.session, self.creds)

    def _make_request(
        self,
        path: str,
        method: Literal["get", "post", "delete"],
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return self._make_request_cls(
            session=self.session,
            creds=self.creds,
            path=path,
            method=method,
            payload=payload,
        )

    @classmethod
    def _make_request_cls(
        cls,
        *,
        session: Session,
        creds: PaypalCredentials,
        path: str,
        method: Literal["get", "post", "delete"],
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = f"{creds.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {cls.get_auth_token_cls(session, creds)}",
            "PayPal-Request-Id": str(uuid4()),
        }

        response = getattr(session, method)(url=url, headers=headers, json=payload)
        response.raise_for_status()

        if not response.text:
            return {}

        return response.json()

    def _get_transaction_status(
        self,
    ) -> entities.RemoteTransactionStatus:
        if self.trx.type == const.TransactionType.DEPOSIT:
            # If transaction is finalized, id_in_payment_system is capture id, and data stored forever on
            # paypal side. Otherwise it's an order id, and data is stored ~3 hours, and after that paypal returns
            # 404.
            capture_id = self.trx.extra.get(
                PaypalTransactionExtraFields.PAYPAL_CAPTURE_ID
            )
            if capture_id:
                url = f"/v2/payments/captures/{capture_id}"
            else:
                order_id = self.trx.extra.get(
                    PaypalTransactionExtraFields.PAYPAL_ORDER_ID
                )
                assert order_id
                url = f"/v2/checkout/orders/{order_id}"

            try:
                response = self._make_request(
                    path=url,
                    method="get",
                )
            except HTTPError as e:
                if e.response.status_code == 404:
                    assert (
                        not capture_id
                    ), f"Received 404 for captured order: {e.response.text}"
                    return entities.RemoteTransactionStatus(
                        raw_data=e.response.json(),
                        operation_status=entities.TransactionStatus.FAILED,
                        id_in_payment_system=None,
                        decline_code="PAYPAL_ORDER_NOT_FOUND",
                    )
                raise

            captures = (
                response.get("purchase_units", [{}])[0]
                .get("payments", {})
                .get("captures", [])
            )
            assert len(captures) <= 1, f"Incorrect response: {response}"

            match response:
                case {
                    "purchase_units": [{"payments": {"captures": captures}}]
                } if captures:
                    amount = captures[0]["amount"]
                case {"purchase_units": purchase_units} if purchase_units:
                    amount = purchase_units[0].get("amount", {})
                case {"amount": amount}:
                    pass
                case _:
                    raise RuntimeError

            result = entities.RemoteTransactionStatus(
                raw_data=response,
                operation_status={
                    "CREATED": entities.TransactionStatus.PENDING,
                    "APPROVED": entities.TransactionStatus.PENDING,
                    "VOIDED": entities.TransactionStatus.REFUNDED,
                    "COMPLETED": entities.TransactionStatus.SUCCESS,
                    "PAYER_ACTION_REQUIRED": entities.TransactionStatus.PENDING,
                }[response["status"]],
                remote_amount=Money(
                    value=amount["value"],
                    currency=amount["currency_code"],
                )
                if amount.get("value")
                else None,
            )

            if result.operation_status == entities.TransactionStatus.SUCCESS:
                if "payer" in response:
                    result.external_account_id = response["payer"]["email_address"]
                else:
                    result.external_account_id = response["payee"]["email_address"]

            return result

        elif self.trx.type == const.TransactionType.WITHDRAWAL:
            response = self._make_request(
                path=f"/v1/payments/payouts/{self.trx.id_in_payment_system}",
                method="get",
            )

            return entities.RemoteTransactionStatus(
                raw_data=response,
                operation_status={
                    "SUCCESS": entities.TransactionStatus.SUCCESS,
                    "FAILED": entities.TransactionStatus.FAILED,
                    "ONHOLD": entities.TransactionStatus.PENDING,
                    "BLOCKED": entities.TransactionStatus.FAILED,
                    "REFUNDED": entities.TransactionStatus.REFUNDED,
                }[response["batch_header"]["batch_status"]],
                remote_amount=Money(
                    value=response["batch_header"]["amount"]["value"],
                    currency=response["batch_header"]["amount"]["currency"],
                ),
                id_in_payment_system=response["batch_header"]["payout_batch_id"],
            )
        else:
            raise RuntimeError

    def get_webhook_id(self) -> Optional[str]:
        response = self._make_request(
            path="/v1/notifications/webhooks",
            method="get",
        )
        # assert (
        #     len(response["webhooks"]) == 1
        # ), f"There should be only one webhook: {response}"
        return response["webhooks"][0]["id"]

    def deposit(self) -> dict[str, Any]:
        assert self.trx.user_data
        assert self.trx.user_data.phone
        assert self.trx.redirect_url, "Redirect URL is required"

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": self.trx.currency,
                        "value": str(self.trx.amount.quantize(Decimal("0.01"))),
                    }
                }
            ],
            "application_context": {
                "return_url": self.trx.redirect_url,
                "cancel_url": self.trx.redirect_url,
            },
            "payer": {
                "email_address": self.trx.user_data.email,
                "name": {
                    "given_name": self.trx.user_data.first_name,
                    "surname": self.trx.user_data.last_name,
                },
                "phone": {
                    "phone_number": {
                        "national_number": prepare_phone(self.trx.user_data.phone)
                    }
                },
                "address": {
                    "address_line_1": self.trx.user_data.address,
                    "admin_area_1": self.trx.user_data.state,
                    "admin_area_2": self.trx.user_data.city,
                    "country_code": self.trx.user_data.country,
                    "postal_code": self.trx.user_data.post_code,
                },
            },
        }

        response = self._make_request(
            path="/v2/checkout/orders",
            method="post",
            payload=payload,
        )
        return response

    def deposit_finalize(self) -> entities.PaymentClientDepositFinalizeResponse:
        try:
            order_id: str | None = self.trx.extra.get(
                PaypalTransactionExtraFields.PAYPAL_ORDER_ID
            )
            assert order_id
            response = self._make_request(
                path=f"/v2/checkout/orders/{order_id}/capture",
                method="post",
                payload={},
            )
        except HTTPError as e:
            resp = e.response.json()
            return entities.PaymentClientDepositFinalizeResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=resp or {},
                decline_code=resp["name"],
                decline_reason=resp["message"],
            )

        return entities.PaymentClientDepositFinalizeResponse(
            status=entities.TransactionStatus.SUCCESS,
            raw_response=response,
        )

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        account = self.trx.withdraw_to_account
        assert account
        payload = {
            "items": [
                {
                    "receiver": account,
                    "amount": {
                        "currency": self.trx.currency,
                        "value": str(self.trx.amount),
                    },
                    "recipient_type": "EMAIL",
                    "sender_item_id": str(self.trx.uuid),
                    "recipient_wallet": "PAYPAL",
                }
            ],
            "sender_batch_header": {
                "sender_batch_id": str(self.trx.uuid),
            },
        }
        response = self._make_request(
            path="/v1/payments/payouts",
            method="post",
            payload=payload,
        )

        return entities.PaymentClientWithdrawResponse(
            status=entities.TransactionStatus.PENDING,
            raw_response=response,
            id_in_payment_system=response["batch_header"]["payout_batch_id"],
        )

    @classmethod
    def setup_webhooks(
        cls,
        url: str,
        creds: PaypalCredentials,
        logger: LogWriter,
        only_clear_existing: bool = False,
        remove_existing: bool = False,
    ) -> None:
        assert url.startswith(settings.EXTERNAL_ROZERT_HOST), f"Invalid URL: {url}"

        # Removing all webhooks
        if remove_existing:
            cls.remove_webhooks(urls_=re.compile(".*"), creds=creds, log_writer=logger)

        if not only_clear_existing:
            # Creating new webhook
            cls._create_webhook(url, creds)

        logger.write("Current webhooks:")
        for webhook in cls.get_webhooks(creds):
            logger.write(f"Webhook: {webhook}")

    @classmethod
    def _remove_webhook(cls, webhook_id: str, creds: PaypalCredentials) -> None:
        cls._make_request_cls(
            path=f"/v1/notifications/webhooks/{webhook_id}",
            method="delete",
            session=requests.Session(),
            creds=creds,
        )

    @classmethod
    def _create_webhook(
        cls, url: str, creds: PaypalCredentials
    ) -> entities.Webhook | None:
        try:
            response = cls._make_request_cls(
                path="/v1/notifications/webhooks",
                method="post",
                payload={"url": url, "event_types": [{"name": "*"}]},
                session=requests.Session(),
                creds=creds,
            )
        except HTTPError as e:
            if e.response.json().get("name") == "WEBHOOK_URL_ALREADY_EXISTS":
                return None
            raise
        return entities.Webhook(
            id=response["id"],
            url=url,
            raw_data=response,
        )

    @classmethod
    def get_webhooks(cls, creds: PaypalCredentials) -> list[entities.Webhook]:
        result = cls._make_request_cls(
            path="/v1/notifications/webhooks",
            method="get",
            session=requests.Session(),
            creds=creds,
        )

        return [
            entities.Webhook(
                id=webhook["id"],
                url=webhook["url"],
                raw_data=webhook,
            )
            for webhook in result["webhooks"]
        ]


class SandboxPaypalClient(
    PaypalClient, base_classes.BaseSandboxClientMixin[PaypalCredentials]
):
    def get_auth_token(self) -> str:
        return "fake"

    def generate_reference(self, *, amount: Decimal, trx_id: str) -> str:
        return "fake"


def get_paypal_id_in_payment_system_from_response(
    response: dict[str, Any]
) -> tuple[str | None, Literal["capture", "order"]]:
    captures = (
        response.get("purchase_units", [{}])[0]
        .get("payments", {})
        .get("captures", [{"id": None}])
    )
    assert len(captures) <= 1, f"Incorrect response: {response}"
    if r := captures[0]["id"]:
        return r, "capture"
    return response.get("id"), "order"


class PaypalController(PaymentSystemController[PaypalClient, SandboxPaypalClient]):
    client_cls = PaypalClient
    sandbox_client_cls = SandboxPaypalClient

    def _run_deposit(
        self, trx_id: int, client: PaypalClient | SandboxPaypalClient
    ) -> None:
        response = client.deposit()
        approve_link = [link for link in response["links"] if link["rel"] == "approve"][
            0
        ]["href"]

        with transaction.atomic():
            locked_trx = db_services.get_transaction(trx_id=trx_id, for_update=True)

            _update_paypal_id_in_payment_system(response, locked_trx)

            # Save redirect form
            locked_trx.form = TransactionExtraFormData(
                action_url=approve_link,
                method="get",
            )
            locked_trx.save()

            transaction_processing.schedule_periodic_status_checks(
                trx=locked_trx,
            )

    @staticmethod
    def get_id_in_payment_system_from_webhook_event_data(data: dict[str, Any]) -> str:
        if "supplementary_data" in data["resource"]:
            return data["resource"]["supplementary_data"]["related_ids"]["order_id"]
        return data["resource"]["id"]

    def _on_deposit_finalization_response_received(
        self,
        response: entities.PaymentClientDepositFinalizeResponse,
        locked_trx: "LockedTransaction",
    ) -> None:
        _update_paypal_id_in_payment_system(response.raw_response, locked_trx)

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        body = json.loads(cb.body)
        order_id_from_callback = self.get_id_in_payment_system_from_webhook_event_data(
            body
        )
        capture_id_from_callback = body.get("resource", {}).get("id", -1)
        trx = PaymentTransaction.objects.select_for_update().get(
            Q(id_in_payment_system=order_id_from_callback)
            | Q(id_in_payment_system=capture_id_from_callback)
        )
        client = self.get_client(trx)

        _validate_paypal_webhook_signature(
            creds=client.creds,
            cb=cb,
            body=body,
            client=client,
        )

        if body["resource"]["status"] == "APPROVED":
            tasks.run_deposit_finalization.delay(trx.id)

            with transaction.atomic():
                locked_trx = db_services.get_transaction(trx_id=trx.id, for_update=True)
                transaction_processing.schedule_periodic_status_checks(
                    trx=locked_trx,
                    until=timezone.now()
                    + timedelta(seconds=trx.system.deposit_allowed_ttl_seconds),
                )

        tasks.check_status.delay(trx.id)
        return RemoteTransactionStatus.initial(
            raw_data={},
            transaction_id=trx.id,
        )

    def _before_sync_remote_status_with_transaction(
        self, trx: "LockedTransaction", remote_status: CleanRemoteTransactionStatus
    ) -> None:
        if remote_status.raw_data.get("status") == "APPROVED":
            tasks.run_deposit_finalization.delay(trx_id=trx.id)

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        # We do not explicitly check the callback signature here because the signature is verified
        # during the callback parsing process in `_parse_callback`. Specifically, the webhook event
        # data is validated using PayPal's `verify-webhook-signature` endpoint, which ensures the
        # integrity and authenticity of the incoming callback.
        return True

    def _run_withdraw(
        self, trx: PaymentTransaction, client: PaypalClient | SandboxPaypalClient
    ) -> None:
        self._execute_withdraw_query(trx, client)

        # Schedule periodic checks
        trx.check_status_until = trx.updated_at + datetime.timedelta(days=1)
        trx.save()

    def _get_action_on_credentials_change(
        self,
    ) -> (
        Callable[
            [Wallet, dict[str, Any], dict[str, Any], LogWriter],
            None | Error,
        ]
        | None
    ):
        def paypal_credentials_change_action(
            _: Wallet,
            old_creds: dict[str, Any],
            new_creds: dict[str, Any],
            internal_logger: LogWriter,
        ) -> Error | None:
            try:
                url = reverse("callback", kwargs=dict(system="paypal"))
                PaypalClient.setup_webhooks(
                    f"{settings.EXTERNAL_ROZERT_HOST}{url}",
                    creds=PaypalCredentials(**new_creds),
                    remove_existing=False,
                    logger=internal_logger,
                )
            except Exception as e:  # pragma: no cover
                logger.warning(
                    f"Error setting up PayPal webhooks after credentials change: {e}",
                )
                return Error(f"Error setting up PayPal webhooks: {e}")

            return None

        return paypal_credentials_change_action


def _update_paypal_id_in_payment_system(
    raw_response: dict[str, ty.Any], locked_trx: "LockedTransaction"
) -> None:
    # We should change id_in_payment_system from order id to capture id, as order_id lives
    # for a short time, and after capture capture_id is used to find transaction.
    id_in_ps, where = get_paypal_id_in_payment_system_from_response(raw_response)
    capture_id = locked_trx.extra.get(PaypalTransactionExtraFields.PAYPAL_CAPTURE_ID)
    order_id = locked_trx.extra.get(PaypalTransactionExtraFields.PAYPAL_ORDER_ID)
    if id_in_ps:
        if where == "capture":
            if capture_id:
                assert (
                    capture_id == id_in_ps
                ), f"Capture id mismatch: {capture_id} != {id_in_ps}"
            locked_trx.id_in_payment_system = id_in_ps
            locked_trx.extra[PaypalTransactionExtraFields.PAYPAL_CAPTURE_ID] = id_in_ps
        elif where == "order":
            if order_id:
                assert (
                    order_id == id_in_ps
                ), f"Order id mismatch: {order_id} != {id_in_ps}"

            if not locked_trx.id_in_payment_system:
                locked_trx.id_in_payment_system = id_in_ps
            locked_trx.extra[PaypalTransactionExtraFields.PAYPAL_ORDER_ID] = id_in_ps
        else:
            raise RuntimeError

        locked_trx.save()


def _validate_paypal_webhook_signature(
    creds: PaypalCredentials,
    cb: IncomingCallback,
    body: dict[str, Any],
    client: PaypalClient,
) -> None:
    for webhook in PaypalClient.get_webhooks(creds):
        verification_body = {
            "transmission_id": cb.headers.get("paypal-transmission-id"),
            "transmission_time": cb.headers.get("paypal-transmission-time"),
            "cert_url": cb.headers.get("paypal-cert-url"),
            "webhook_id": webhook.id,
            "transmission_sig": cb.headers.get("paypal-transmission-sig"),
            "auth_algo": cb.headers.get("paypal-auth-algo"),
            "webhook_event": body,
        }

        response = client._make_request(
            path="/v1/notifications/verify-webhook-signature",
            payload=verification_body,
            method="post",
        )

        if response.get("verification_status") == "SUCCESS":
            return

    raise ValidationError("Invalid PayPal webhook signature.")


class PaypalWithdrawalTransactionRequestSerializer(  # type: ignore[misc]
    serializers.WithdrawalTransactionRequestSerializer,
    serializers.UserDataSerializerMixin,
):
    pass


paypal_controller = PaypalController(
    payment_system=const.PaymentSystemType.PAYPAL,
    default_credentials={
        "base_url": "https://fake.com",
        "client_id": "fake",
        "client_secret": "fake",
        "test_mode": True,
    },
)


class PaypalDepositSerializer(  # type: ignore[misc]
    serializers.DepositTransactionRequestSerializer, serializers.UserDataSerializerMixin
):
    def _get_extra(self) -> dict[str, Any]:
        return {
            "stp_codi_type": self.validated_data["type"],
        }


@extend_schema(
    tags=["PayPal"],
)
class PaypalViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[Any],
):
    @extend_schema(
        operation_id="Create PayPal deposit transaction",
        request=PaypalDepositSerializer,
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data, serializer_class=PaypalDepositSerializer
        )

    @extend_schema(
        operation_id="Create Paypal withdrawal transaction",
        summary="Create withdrawal transaction",
        description=f"""
Creates new withdrawal from merchant wallet to customer account.
Supported by: {", ".join(const.PAYMENT_SYSTEMS_WITH_WITHDRAWALS)}
        """,
        request=PaypalWithdrawalTransactionRequestSerializer(),
    )
    @action(detail=False, methods=["post"])
    def withdraw(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data,
            PaypalWithdrawalTransactionRequestSerializer,
        )
