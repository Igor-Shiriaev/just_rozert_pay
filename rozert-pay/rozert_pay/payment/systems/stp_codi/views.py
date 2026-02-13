from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.payment.api_v1.serializers import DepositTransactionRequestSerializer
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.payment.models import PaymentTransaction
from rozert_pay.payment.systems.stp_codi.entities import StpCodiDepositType


class StpCodiSerializer(DepositTransactionRequestSerializer):
    class UserDataSerializer(serializers.Serializer):
        phone = serializers.CharField()

    user_data = UserDataSerializer()
    deposit_type = serializers.ChoiceField(
        choices=StpCodiDepositType.choices, default=StpCodiDepositType.APP
    )

    def _get_extra(self) -> dict[str, Any]:
        return {
            "stp_codi_type": self.validated_data["deposit_type"],
        }

    @classmethod
    def get_stp_codi_type(cls, trx: PaymentTransaction) -> StpCodiDepositType:
        return StpCodiDepositType(trx.extra["stp_codi_type"])


@extend_schema(
    tags=["STP CODI"],
)
class StpCodiViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet,
):
    @extend_schema(
        operation_id="Create STP CODI deposit transaction",
        request=StpCodiSerializer,
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(request.data, serializer_class=StpCodiSerializer)
