import logging
import time
import typing as ty
from functools import cached_property
from pathlib import Path

import requests
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from pydantic import BaseModel
from rest_framework import serializers as rest_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common.types import AuthorizedRequest
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.api_v1.serializers import TransactionResponseSerializer
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.payment.models import PaymentTransaction, Wallet
from rozert_pay.payment.systems.cardpay_systems.cardpay_applepay.client import (
    CardpayApplepayCreds,
)

logger = logging.getLogger(__name__)


class CardpayApplepayExtra(BaseModel):
    encrypted_data: str


class CardpayApplepayDepositSerializer(  # type: ignore[misc]
    serializers.DepositTransactionRequestSerializer,
    serializers.UserDataSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    encrypted_data = rest_serializers.CharField(
        required=True, help_text="This data should be passed from client side"
    )

    @classmethod
    def get_extra(cls, trx: PaymentTransaction) -> CardpayApplepayExtra:
        return CardpayApplepayExtra(**trx.extra)

    def _get_extra_fields(self) -> list[str]:
        return ["encrypted_data"]


class CardpayApplepayWithdrawSerializer(  # type: ignore[misc]
    serializers.WithdrawalTransactionRequestSerializer,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    encrypted_data = rest_serializers.CharField(
        required=True, help_text="This data should be passed from client side"
    )
    withdraw_to_account = None  # type: ignore[assignment]

    def _get_extra_fields(self) -> list[str]:
        return ["encrypted_data"]


class CardpayApplepayMerchantValidationRequestSerializer(rest_serializers.Serializer):
    merchant_identifier = rest_serializers.CharField()
    domain = rest_serializers.CharField()
    validation_url = rest_serializers.URLField()
    wallet_id = rest_serializers.UUIDField()


class CardpayApplepayMerchantValidationResponseSerializer(rest_serializers.Serializer):
    pass


class _CredsWrapper:
    def __init__(self, creds: "CardpayApplepayCreds", wallet_uuid: str):
        self.creds = creds
        self._certificate_file = Path(f"/tmp/{wallet_uuid}.crt")
        self._key_file = Path(f"/tmp/{wallet_uuid}.key")
        self.last_fs_write_operation: float | None = None

    @cached_property
    def certificate_path(self) -> str:
        if not self._certificate_file.exists():
            self._certificate_file.write_text(self.creds.applepay_certificate)
            self.last_fs_write_operation = time.time()
        return str(self._certificate_file)

    @cached_property
    def key_path(self) -> str:
        if not self._key_file.exists():
            self._key_file.write_text(self.creds.applepay_key)
            self.last_fs_write_operation = time.time()
        return str(self._key_file)

    def clean(self) -> None:
        if self._certificate_file.exists():
            self._certificate_file.unlink()
        if self._key_file.exists():
            self._key_file.unlink()


@extend_schema(
    tags=["Cardpay Applepay"],
)
class CardpayApplepayViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[ty.Any],
):
    @extend_schema(
        operation_id="cardpay_applepay.deposit",
        summary="Create cardpay applepay deposit transaction",
        request=CardpayApplepayDepositSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data,
            serializer_class=CardpayApplepayDepositSerializer,
        )

    @extend_schema(
        operation_id="cardpay_applepay.withdraw",
        summary="Create Cardpay Applepay withdrawal transaction",
        request=CardpayApplepayWithdrawSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def withdraw(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data, serializer_class=CardpayApplepayWithdrawSerializer
        )

    @extend_schema(
        operation_id="cardpay_applepay.merchant_validation",
        summary="Merchant validation",
        request=CardpayApplepayMerchantValidationRequestSerializer,
        responses={
            200: CardpayApplepayMerchantValidationResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def merchant_validation(self, request: AuthorizedRequest) -> HttpResponse:
        serializer = CardpayApplepayMerchantValidationRequestSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        request_data = {
            "merchantIdentifier": serializer.validated_data["merchant_identifier"],
            "displayName": "Betmaster",
            "initiative": "web",
            "initiativeContext": serializer.validated_data["domain"],
        }
        wallet_id = serializer.validated_data["wallet_id"]
        wallet = Wallet.objects.get(
            merchant=request.auth.merchant,
            uuid=wallet_id,
        )
        creds_wrapper = _CredsWrapper(
            CardpayApplepayCreds(**wallet.credentials), str(wallet.uuid)
        )

        validation_url = serializer.validated_data["validation_url"]
        response = requests.post(
            validation_url,
            json=request_data,
            cert=(creds_wrapper.certificate_path, creds_wrapper.key_path),
        )

        passed, parsed_response = response.status_code == 200, response.text

        if not passed:
            raise ValidationError("merchant validation not passed")

        return HttpResponse(
            content=parsed_response,
        )
