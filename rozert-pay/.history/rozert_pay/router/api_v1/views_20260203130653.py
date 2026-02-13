from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const, types
from rozert_pay.common.authorization import HMACAuthentication
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.router.services import routing

from .serializers import (
    RoutedDepositTransactionSerializer,
    RouterDepositRequestSerializer,
)


@extend_schema(tags=["Router"])
class RouterDepositViewSet(
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
):
    request: types.AuthorizedRequest

    permission_classes = [IsAuthenticated]
    authentication_classes = [HMACAuthentication]
    serializer_class = RouterDepositRequestSerializer

    @extend_schema(
        summary="Create routed deposit",
        description="Automatically selects the best provider wallet based on routing rules.",
    )
    def create(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        card_info = validated_data.get("card_data") or {}

        try:
            routing_result = routing.get_best_wallet(
                {
                    "merchant": self.request.auth.merchant,
                    "merchant_terminal_uuid": validated_data["merchant_terminal_id"],
                    "amount": validated_data["amount"],
                    "currency": str(validated_data["currency"]).upper(),
                    "method_type": validated_data["method_type"],
                    "transaction_type": const.TransactionType.DEPOSIT,
                    "bank_id": card_info.get("bank_id"),
                    "country": card_info.get("country"),
                }
            )
        except ValueError as e:
            raise ValidationError({"routing": str(e)})

        selected_wallet = routing_result["wallet"]

        deposit_data: dict[str, Any] = {
            "wallet_id": str(selected_wallet.uuid),
            "amount": validated_data["amount"],
            "currency": str(validated_data["currency"]).upper(),
            "merchant_terminal_id": routing_result["merchant_terminal_id"],
            "provider_terminal_id": routing_result["paymentsystem_terminal_id"],
            "routing_rule_id": routing_result["routing_rule_id"],
        }

        if validated_data.get("customer_id") is not None:
            deposit_data["customer_id"] = validated_data["customer_id"]

        if validated_data.get("redirect_url") is not None:
            deposit_data["redirect_url"] = validated_data["redirect_url"]

        if validated_data.get("callback_url") is not None:
            deposit_data["callback_url"] = validated_data["callback_url"]

        if validated_data.get("user_data") is not None:
            deposit_data["user_data"] = validated_data["user_data"]

        if validated_data.get("card_data") is not None:
            deposit_data["card_data"] = validated_data["card_data"]

        return self._generic_deposit(
            data=deposit_data,
            serializer_class=RoutedDepositTransactionSerializer,
        )
