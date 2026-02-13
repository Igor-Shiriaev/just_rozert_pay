from __future__ import annotations

import typing as ty
from typing import TYPE_CHECKING

from drf_spectacular.utils import extend_schema
from rest_framework import serializers as rest_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.api_v1.serializers import TransactionResponseSerializer
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin

if TYPE_CHECKING:
    pass


class WorldpayDepositSerializer(  # type: ignore[misc]
    serializers.DepositTransactionRequestSerializer,
    serializers.CardSerializerMixin,
    serializers.user_data_serializer_mixin_factory(  # type: ignore[misc]
        "WorldpayUserData",
        required_fields=[
            "first_name",
            "last_name",
            "email",
            "post_code",
            "city",
            "country",
        ],
    ),
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )


class WorldpayCardWithdrawSerializer(  # type: ignore[misc]
    serializers.WithdrawalTransactionRequestSerializer,
    serializers.CardNoCVVSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    withdraw_to_account = None  # type: ignore[assignment]


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
        operation_id="worldpay.withdraw.card-data",
        summary="Create Worldpay withdrawal transaction by card data",
        request=WorldpayCardWithdrawSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"], url_path="withdraw/card-data")
    def withdraw_by_card(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data, serializer_class=WorldpayCardWithdrawSerializer
        )
