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


class CardpayBankcardDepositSerializer(  # type: ignore[misc]
    serializers.DepositTransactionRequestSerializer,
    serializers.CardSerializerMixin,
    serializers.UserDataSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    user_data = custom_user_data_serializer(
        "CardpayBankcardWithdrawUserData", required_fields=["email"]
    )


class CardpayBankcardDepositByTokenSerializer(  # type: ignore[misc]
    serializers.DepositTransactionRequestSerializer,
    serializers.CardTokenSerializerMixin,
    serializers.UserDataSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    user_data = custom_user_data_serializer(
        "CardpayBankcardWithdrawUserData", required_fields=["email"]
    )


class CardpayBankcardWithdrawSerializer(  # type: ignore[misc]
    serializers.WithdrawalTransactionRequestSerializer,
    serializers.CardNoCVVSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    withdraw_to_account = None  # type: ignore[assignment]
    user_data = custom_user_data_serializer(  # type: ignore[assignment]
        "CardpayBankcardWithdrawUserData", required_fields=["email"]
    )


class CardpayBankcardWithdrawByTokenSerializer(  # type: ignore[misc]
    serializers.WithdrawalTransactionRequestSerializer,
    serializers.CardTokenSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    withdraw_to_account = None  # type: ignore[assignment]


@extend_schema(
    tags=["Cardpay Bankcard"],
)
class CardpayBankcardViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[ty.Any],
):
    @extend_schema(
        operation_id="cardpay_cards.deposit",
        summary="Create deposit transaction",
        request=CardpayBankcardDepositSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data,
            serializer_class=CardpayBankcardDepositSerializer,
        )

    @extend_schema(
        operation_id="cardpay_cards.deposit",
        summary="Create deposit transaction using card token from previous deposits",
        request=CardpayBankcardDepositByTokenSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def deposit_card_token(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data,
            serializer_class=CardpayBankcardDepositByTokenSerializer,
        )

    @extend_schema(
        operation_id="cardpay_cards.withdraw.card-data",
        summary="Create Cardpay Bankcard withdrawal transaction by card data",
        request=CardpayBankcardWithdrawSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"], url_path="withdraw/card-data")
    def withdraw_by_card(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data, serializer_class=CardpayBankcardWithdrawSerializer
        )

    @extend_schema(
        operation_id="cardpay_cards.withdraw.card-token",
        summary="Create Cardpay Bankcard withdrawal transaction by card token.",
        description="""
Card token can be obtained from first successfull deposit transaction.
See card_token parameter in transaction response.
    """,
        request=CardpayBankcardWithdrawByTokenSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"], url_path="withdraw/card-token")
    def withdraw_by_token(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data, serializer_class=CardpayBankcardWithdrawByTokenSerializer
        )
