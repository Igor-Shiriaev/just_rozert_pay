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
        data = serializer.validated_data
        card_data = data.get("card_data") or {}

        try:
            result = routing.get_best_wallet(
                {
                    "merchant": self.request.auth.merchant,
                    "merchant_terminal_uuid": data["merchant_terminal_id"],
                    "amount": data["amount"],
                    "currency": str(data["currency"]).upper(),
                    "method_type": data["method_type"],
                    "transaction_type": const.TransactionType.DEPOSIT,
                    "bank_id": card_data.get("bank_id"),
                    "country": card_data.get("country"),
                }
            )
        except ValueError as e:
            raise ValidationError({"routing": str(e)})

        wallet = result["wallet"]

        payment_data: dict[str, Any] = {
            "wallet_id": str(wallet.uuid),
            "amount": data["amount"],
            "currency": str(data["currency"]).upper(),
            "merchant_terminal_id": result["merchant_terminal_id"],
            "provider_terminal_id": result["paymentsystem_terminal_id"],
            "routing_rule_id": result["routing_rule_id"],
        }

        if data.get("customer_id") is not None:
            payment_data["customer_id"] = data["customer_id"]

        if data.get("redirect_url") is not None:
            payment_data["redirect_url"] = data["redirect_url"]

        if data.get("callback_url") is not None:
            payment_data["callback_url"] = data["callback_url"]

        if data.get("user_data") is not None:
            payment_data["user_data"] = data["user_data"]

        if data.get("card_data") is not None:
            payment_data["card_data"] = data["card_data"]

        return self._generic_deposit(
            data=payment_data,
            serializer_class=RoutedDepositTransactionSerializer,
        )
