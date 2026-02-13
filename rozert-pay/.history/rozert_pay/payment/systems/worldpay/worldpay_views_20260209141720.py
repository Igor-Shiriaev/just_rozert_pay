import typing as ty
from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers as rest_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.common.types import AuthorizedRequest
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.api_v1.serializers import (
    TransactionResponseSerializer,
    user_data_serializers,
)
from rozert_pay.payment.api_v1.serializers.card_serializers import (
    CardBrowserDataSerializer,
)
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.payment.models import Wallet
from rozert_pay.payment.systems.worldpay.const import WorldpayTransactionExtraFields
from rozert_pay.payment.systems.worldpay.helpers import generate_ddc_jwt
from rozert_pay.payment.systems.worldpay.worldpay_client import WorldpayClient

WorldpayUserDataSerializer = user_data_serializers.custom_user_data_serializer(
    "WorldpayUserDataSerializer",
    [
        "email",
        "address",
        "city",
        "post_code",
        "country",
        "ip_address",
        "phone",
    ],
)


class WorldpayDepositSerializer(  # type: ignore[misc]
    serializers.DepositTransactionRequestSerializer,
    serializers.CardSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    user_data = WorldpayUserDataSerializer
    browser_data = CardBrowserDataSerializer(required=True)
    session_id = rest_serializers.CharField(
        required=True,
        max_length=100,
    )
    is_3ds_enabled = rest_serializers.BooleanField(
        required=True,
        default=True,
    )

    def _get_extra_fields(self) -> list[str]:
        return [  # pragma: no cover
            CardBrowserDataSerializer.EXTRA_FIELD,
            WorldpayTransactionExtraFields.SESSION_ID,
        ]

    def _get_extra(self) -> dict[str, Any]:
        return {
            CardBrowserDataSerializer.EXTRA_FIELD: self.validated_data["browser_data"],
            WorldpayTransactionExtraFields.SESSION_ID: self.validated_data[
                "session_id"
            ],
        }


class DDCJwtResponseSerializer(rest_serializers.Serializer[ty.Any]):
    jwt_token = rest_serializers.CharField(
        help_text="DDC JWT token for device data collection",
    )


# class WorldpayCardWithdrawSerializer(  # type: ignore[misc]
#     serializers.WithdrawalTransactionRequestSerializer,
#     serializers.CardNoCVVSerializerMixin,
# ):
#     customer_id = rest_serializers.CharField(
#         help_text="Customer unique ID",
#     )
#     withdraw_to_account = None  # type: ignore[assignment]


@extend_schema(
    tags=["Worldpay"],
)
class WorldpayViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[ty.Any],
):
    @extend_schema(
        operation_id="worldpay.deposit",
        summary="Create Worldpay deposit transaction",
        request=WorldpayDepositSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data, serializer_class=WorldpayDepositSerializer
        )

    @extend_schema(
        operation_id="worldpay.ddc_jwt",
        summary="Generate JWT for DDC (Device Data Collection) step",
        responses={200: DDCJwtResponseSerializer},
    )
    @action(detail=False, methods=["get"], url_path="ddc-jwt")
    def ddc_jwt(self, request: AuthorizedRequest) -> Response:
        wallet = Wallet.objects.filter(
            merchant=request.auth.merchant,
            system__type=const.PaymentSystemType.WORLDPAY,
        ).first()

        if not wallet:
            raise NotFound("Worldpay wallet not found for this merchant")

        creds = WorldpayClient.parse_and_validate_credentials(wallet.credentials)

        jwt_token_for_ddc = generate_ddc_jwt(
            jwt_issuer=creds.jwt_issuer,
            jwt_org_unit_id=creds.jwt_org_unit_id,
            jwt_mac_key=creds.jwt_mac_key,
        )

        return Response(
            DDCJwtResponseSerializer(instance={"jwt_token": jwt_token_for_ddc}).data,
        )

    # @extend_schema(
    #     operation_id="worldpay.withdraw.card-data",
    #     summary="Create Worldpay withdrawal transaction by card data",
    #     request=WorldpayCardWithdrawSerializer,
    #     responses={
    #         200: TransactionResponseSerializer,
    #     },
    # )
    # @action(detail=False, methods=["post"], url_path="withdraw/card-data")
    # def withdraw_by_card(self, request: Request) -> Response:
    #     return self._generic_withdraw(
    #         request.data, serializer_class=WorldpayCardWithdrawSerializer
    #     )
