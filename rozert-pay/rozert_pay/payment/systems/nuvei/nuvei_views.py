import typing as ty

from drf_spectacular.utils import extend_schema
from rest_framework import serializers as rest_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.api_v1.serializers import TransactionResponseSerializer
from rozert_pay.payment.api_v1.serializers.user_data_serializers import (
    custom_user_data_serializer,
)
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin

NuveiUserDataSerializer = custom_user_data_serializer(
    "NuveiUserDataSerializer", required_fields=["email", "country", "ip_address"]
)


class NuveiDepositSerializer(  # type: ignore[misc]
    serializers.DepositTransactionRequestSerializer,
    serializers.CardSerializerMixin,
    serializers.UserDataSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    user_data = NuveiUserDataSerializer


class NuveiWithdrawSerializer(  # type: ignore[misc]
    serializers.WithdrawalTransactionRequestSerializer,
    serializers.CardNoCVVSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    withdraw_to_account = None  # type: ignore[assignment]
    user_data = NuveiUserDataSerializer  # type: ignore[assignment]


@extend_schema(
    tags=["Nuvei"],
)
class NuveiViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[ty.Any],
):
    @extend_schema(
        operation_id="nuvei.deposit",
        summary="Create Nuvei deposit transaction",
        request=NuveiDepositSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data,
            serializer_class=NuveiDepositSerializer,
        )

    @extend_schema(
        operation_id="nuvei.withdraw.card-data",
        summary="Create Nuvei withdrawal transaction by card data",
        request=NuveiWithdrawSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"], url_path="withdraw/card-data")
    def withdraw_by_card(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data, serializer_class=NuveiWithdrawSerializer
        )
