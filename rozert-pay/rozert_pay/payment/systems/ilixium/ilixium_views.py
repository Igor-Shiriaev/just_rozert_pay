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
from rozert_pay.payment.api_v1.serializers import (
    TransactionResponseSerializer,
    user_data_serializers,
)
from rozert_pay.payment.api_v1.serializers.card_serializers import (
    CardBrowserDataSerializer,
)
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin

if TYPE_CHECKING:
    pass


IlixiumUserDataSerializer = user_data_serializers.custom_user_data_serializer(
    "IlixiumUserDataSerializer",
    [
        "email",
        "language",
        "first_name",
        "last_name",
        "address",
        "city",
        "post_code",
        "country",
        "phone",
        "ip_address",
    ],
)

IlixiumUserDataWithdrawSerializer = user_data_serializers.custom_user_data_serializer(
    "IlixiumUserDataSerializer",
    [
        "email",
        "first_name",
        "last_name",
        "address",
        "city",
        "post_code",
        "country",
        "phone",
        "date_of_birth",
    ],
)


class IlixiumDepositSerializer(  # type: ignore[misc]
    serializers.DepositTransactionRequestSerializer,
    serializers.CardSerializerMixin,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    user_data = IlixiumUserDataSerializer
    browser_data = CardBrowserDataSerializer(required=True)

    def _get_extra_fields(self) -> list[str]:
        return [CardBrowserDataSerializer.EXTRA_FIELD]


class IlixiumWithdrawSerializer(  # type: ignore[misc]
    serializers.WithdrawalTransactionRequestSerializer,
):
    customer_id = rest_serializers.CharField(
        help_text="Customer unique ID",
    )
    withdraw_to_account = None  # type: ignore[assignment]
    beneficiary_account_number = rest_serializers.CharField()
    beneficiary_bank_code = rest_serializers.CharField()
    beneficiary_sort_code = rest_serializers.CharField()
    user_data = IlixiumUserDataWithdrawSerializer  # type: ignore[assignment]

    def _get_extra_fields(self) -> list[str]:
        return [
            "beneficiary_sort_code",
            "beneficiary_bank_code",
            "beneficiary_account_number",
        ]


@extend_schema(
    tags=["Ilixium"],
)
class IlixiumViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[ty.Any],
):
    @extend_schema(
        operation_id="ilixium.deposit",
        summary="Create Ilixium deposit transaction",
        request=IlixiumDepositSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data, serializer_class=IlixiumDepositSerializer
        )

    @extend_schema(
        operation_id="ilixium.withdraw",
        summary="Create Ilixium withdrawal transaction",
        request=IlixiumWithdrawSerializer,
        responses={
            200: TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"], url_path="withdraw")
    def withdraw(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data, serializer_class=IlixiumWithdrawSerializer
        )
