import typing as ty

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.common.types import AuthorizedRequest
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.api_v1.serializers.user_data_serializers import (
    custom_user_data_serializer,
)
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.payment.systems.bitso_spei import bitso_spei_client_sandbox
from rozert_pay.payment.systems.bitso_spei.client import BitsoSpeiClient


class BitsoWithdrawalTransactionRequestSerializer(
    serializers.WithdrawalTransactionRequestSerializer,
):
    user_data = custom_user_data_serializer(  # type: ignore[assignment]
        "BitsoWithdrawalSerializer", ["first_name", "last_name"], required=False
    )


@extend_schema(tags=["Bitso SPEI"])
class BitsoSpeiViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[ty.Any],
):
    @extend_schema(
        operation_id="Create Bitso SPEI deposit instruction",
        description="""
Request to create specific account for Bitso SPEI deposit for merchant customer.
New account is created for each new customer_id.

Client should deposit funds to provided account.
When client made a deposit, callback will be sent to merchant.""",
        responses={
            200: serializers.DepositAccountInstructionResponseSerializer,
        },
        request=serializers.RequestInstructionSerializer,
    )
    @action(detail=False, methods=["post"])
    def create_instruction(self, request: AuthorizedRequest) -> Response:
        return self._generic_create_instruction(
            request=request,
            account_creator=BitsoSpeiClient.create_deposit_instruction,
            sandbox_client_cls=bitso_spei_client_sandbox.BitsoSpeiClientSandbox,
            system_type=const.PaymentSystemType.BITSO_SPEI,
        )

    @extend_schema(
        operation_id="Create STP SPEI withdrawal transaction",
        request=BitsoWithdrawalTransactionRequestSerializer,
    )
    @action(detail=False, methods=["post"])
    def withdraw(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data,
            BitsoWithdrawalTransactionRequestSerializer,
        )
