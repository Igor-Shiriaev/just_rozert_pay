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


class AppexDepositSerializer(  # type: ignore[misc]
    serializers.DepositTransactionRequestSerializer,
    serializers.CardSerializerMixin,
    serializers.user_data_serializer_mixin_factory(  # type: ignore[misc]
        required_fields=["email", "language"]
    ),
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )


class AppexCardWithdrawSerializer(  # type: ignore[misc]
    serializers.WithdrawalTransactionRequestSerializer,
    serializers.CardNoCVVSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    withdraw_to_account = None  # type: ignore[assignment]


class AppexCardTokenWithdrawSerializer(  # type: ignore[misc]
    serializers.WithdrawalTransactionRequestSerializer,
    serializers.CardTokenSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    withdraw_to_account = None  # type: ignore[assignment]


@extend_schema(
    tags=["Appex"],
)
class AppexViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[ty.Any],
):
    @extend_schema(
        operation_id="appex.deposit",
        summary="Create Appex deposit transaction",
        request=AppexDepositSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data, serializer_class=AppexDepositSerializer
        )

    @extend_schema(
        operation_id="appex.withdraw.card-data",
        summary="Create Appex withdrawal transaction by card data",
        request=AppexCardWithdrawSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"], url_path="withdraw/card-data")
    def withdraw_by_card(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data, serializer_class=AppexCardWithdrawSerializer
        )

    @extend_schema(
        operation_id="appex.withdraw.card-token",
        summary="Create Appex withdrawal transaction by card token.",
        description="""
Card token can be obtained from first successfull deposit transaction.
See card_token parameter in transaction response.
""",
        request=AppexCardTokenWithdrawSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"], url_path="withdraw/card-token")
    def withdraw_by_token(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data, serializer_class=AppexCardTokenWithdrawSerializer
        )
