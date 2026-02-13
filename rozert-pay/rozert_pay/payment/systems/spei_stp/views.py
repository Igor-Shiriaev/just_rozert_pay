from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers as rest_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.common.types import AuthorizedRequest
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.payment.systems.spei_stp import spei_stp_helpers
from rozert_pay.payment.systems.spei_stp.spei_stp_client import SpeiStpSandboxClient


@extend_schema(tags=["STP SPEI"])
class StpSpeiViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[Any],
):
    class _InstructionResponse(rest_serializers.Serializer):
        deposit_account = rest_serializers.CharField(
            help_text="Deposit account number for customer",
            required=True,
        )
        customer_id = rest_serializers.UUIDField(
            help_text="Customer ID on Rozert side",
            required=True,
        )

        class Meta:
            fields = ("deposit_account",)

    @extend_schema(
        operation_id="Create STP SPEI deposit instruction",
        description="""
Request to create specific account for deposit for merchant client.
New account is created for each new customer_id.

Client should deposit funds to provided account.
When client made a deposit, callback will be sent to merchant""",
        responses={
            200: _InstructionResponse,
        },
        request=serializers.RequestInstructionSerializer,
    )
    @action(detail=False, methods=["post"])
    def create_instruction(self, request: AuthorizedRequest) -> Response:
        return self._generic_create_instruction(
            request=request,
            account_creator=spei_stp_helpers.create_deposit_account_and_spei_transaction_for_user,
            sandbox_client_cls=SpeiStpSandboxClient,
            system_type=const.PaymentSystemType.STP_SPEI,
        )

    @extend_schema(
        operation_id="Create STP SPEI withdrawal transaction",
        request=serializers.WithdrawalTransactionRequestSerializer,
    )
    @action(detail=False, methods=["post"])
    def withdraw(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data,
            serializers.WithdrawalTransactionRequestSerializer,
        )
