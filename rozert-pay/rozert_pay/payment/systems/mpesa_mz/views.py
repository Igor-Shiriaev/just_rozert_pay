from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.payment.api_v1.serializers import (
    DepositTransactionRequestSerializer,
    WithdrawalTransactionRequestSerializer,
)
from rozert_pay.payment.api_v1.serializers.user_data_serializers import (
    custom_user_data_serializer,
)
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin


class MpesaMzDepositSerializer(  # type: ignore[misc]
    DepositTransactionRequestSerializer,
):
    user_data = custom_user_data_serializer(
        "MpesaMzDepositUserData", required_fields=["phone"]
    )

    def _get_extra(self) -> dict[str, Any]:
        return {}


class MpesaMzWithdrawSerializer(  # type: ignore[misc]
    WithdrawalTransactionRequestSerializer,
):
    def _get_extra(self) -> dict[str, Any]:
        return {}


@extend_schema(
    tags=["M-Pesa MZ"],
)
class MpesaMzViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet,
):
    @extend_schema(
        operation_id="Create deposit transaction (Mpesa MZ)",
        request=MpesaMzDepositSerializer,
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data,
            serializer_class=MpesaMzDepositSerializer,
        )

    @extend_schema(
        operation_id="Create withdrawal transaction (Mpesa MZ)",
        request=MpesaMzWithdrawSerializer,
    )
    @action(detail=False, methods=["post"])
    def withdraw(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data,
            serializer_class=MpesaMzWithdrawSerializer,
            use_our_uuid_for_customer_external_account_to_withdraw=True,
        )
