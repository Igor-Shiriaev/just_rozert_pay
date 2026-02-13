from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers as rest_serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.common.types import AuthorizedRequest
from rozert_pay.payment import models, types
from rozert_pay.payment.api_v1 import serializers
from rozert_pay.payment.api_v1.serializers.user_data_serializers import (
    custom_user_data_serializer,
)
from rozert_pay.payment.api_v1.views import GenericPaymentSystemApiV1Mixin
from rozert_pay.payment.services import errors
from rozert_pay.payment.services.incoming_callbacks import get_rozert_callback_url
from rozert_pay.payment.systems.muwe_spei.client import (
    MuweSpeiClient,
    MuweSpeiClientSandbox,
)


class MuweSpeiWithdrawalTransactionRequestSerializer(
    serializers.WithdrawalTransactionRequestSerializer,
):
    user_data = custom_user_data_serializer(  # type: ignore[assignment]
        "MuweSpeiWithdrawUserData",
        required_fields=["first_name", "last_name"],
    )


@extend_schema(tags=["MUWE SPEI"])
class MuweSpeiViewSet(  # type: ignore[misc]
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[Any],
):
    """
    ViewSet for MUWE SPEI payment system.

    Provides endpoints for:
    - Creating deposit instructions (CLABE generation)
    - Creating withdrawal transactions
    """

    class _InstructionResponse(rest_serializers.Serializer):
        deposit_account = rest_serializers.CharField(
            help_text="CLABE (18-digit account number) for customer deposits",
            required=True,
        )
        customer_id = rest_serializers.UUIDField(
            help_text="Customer ID on Rozert side",
            required=True,
        )

        class Meta:
            fields = ("deposit_account", "customer_id")

    @extend_schema(
        operation_id="Create MUWE SPEI deposit instruction",
        description="""
Create or retrieve CLABE (18-digit account number) for MUWE SPEI deposits.

**Behavior**:
- If customer already has a CLABE for this wallet, returns the existing one (idempotent)
- If not, generates a new CLABE via MUWE API
- MUWE API is idempotent: same customer ID always returns the same CLABE

**Usage**:
1. Customer requests deposit instruction
2. Backend returns CLABE
3. Customer makes SPEI transfer to this CLABE
4. MUWE sends webhook notification
5. Funds are credited to customer's account

**Note**: CLABE is permanently bound to customer once generated.
        """,
        responses={
            200: _InstructionResponse,
        },
        request=serializers.RequestInstructionSerializer,
    )
    @action(detail=False, methods=["post"])
    def create_instruction(self, request: AuthorizedRequest) -> Response:
        """
        Create or retrieve CLABE for customer deposits.
        """

        def account_creator_with_notify_url(
            *,
            external_customer_id: types.ExternalCustomerId,
            wallet: models.Wallet,
            creds: types.T_Credentials,
        ) -> str | errors.Error:
            notify_url = get_rozert_callback_url(wallet.system)
            return MuweSpeiClient.create_deposit_instruction(
                external_customer_id=external_customer_id,
                wallet=wallet,
                creds=creds,
                notify_url=notify_url,
            )

        return self._generic_create_instruction(
            request=request,
            account_creator=account_creator_with_notify_url,
            sandbox_client_cls=MuweSpeiClientSandbox,
            system_type=const.PaymentSystemType.MUWE_SPEI,
        )

    @extend_schema(
        operation_id="Create MUWE SPEI withdrawal transaction",
        description="""
Create a withdrawal transaction via MUWE SPEI.

**Requirements**:
- Customer must have a verified external account (CLABE + bank info)
- External account must include:
  - `unique_account_number`: Customer's CLABE (18 digits)
  - `extra.bankCode`: Bank code (e.g., "40014")
  - `extra.accountName`: Account holder name (optional, uses full_name if not set)

**Flow**:
1. Withdrawal request is validated
2. MUWE api is called to initiate payout
3. Transaction status is updated via webhook
4. Funds are sent to customer's CLABE

**Status updates**:
- Initial: PENDING
- On webhook: SUCCESS or FAILED
        """,
        request=MuweSpeiWithdrawalTransactionRequestSerializer,
        responses={
            200: serializers.TransactionResponseSerializer,
        },
    )
    @action(detail=False, methods=["post"])
    def withdraw(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data,
            MuweSpeiWithdrawalTransactionRequestSerializer,
        )
