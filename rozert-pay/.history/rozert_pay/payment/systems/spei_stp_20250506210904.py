import json
import logging
from decimal import Decimal
from typing import Any

from django.db import models, transaction
from django.db.models.functions import Cast
from pydantic import BaseModel
from rest_framework.exceptions import ValidationError
from rest_framework.validators import UniqueTogetherValidator
from rozert_pay.common import const
from rozert_pay.common.const import CallbackType, TransactionStatus, TransactionType
from rozert_pay.common.helpers.validation_mexico import calculate_clabe_check_digit
from rozert_pay.payment.api_v1.serializers import (
    BaseAccountSerializer,
    DepositTransactionRequestSerializer,
)
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import DepositAccount, IncomingCallback, Wallet
from rozert_pay.payment.services.base_classes import (
    BasePaymentClient,
    BaseSandboxClientMixin,
)
from rozert_pay.payment.systems.base_controller import PaymentSystemController
from rozert_pay.payment.types import T_Client, T_SandboxClient

logger = logging.getLogger(__name__)


def _get_deposit_account_for_clabe(clabe: str, mask: str) -> str:
    c = int(clabe)
    deposit_account = mask.format(clabe=f"{c:05}")
    deposit_account += str(calculate_clabe_check_digit(deposit_account))
    return deposit_account


def get_clabe_from_deposit_account(deposit_account: str) -> str:
    return deposit_account[-6:-1]


class SpeiCredentials(BaseModel):
    mask: str

    def clean(self) -> None:
        if "{clabe}" not in self.mask:
            raise RuntimeError('mask must contain "{clabe}" placeholder')

        if len(self.mask.replace("{clabe}", "")) != 12:
            raise RuntimeError("mask must be 12 characters long (except placeholder)")


class SpeiClient(BasePaymentClient[SpeiCredentials]):
    pass


class SpeiSandBoxClient(SpeiClient, BaseSandboxClientMixin[SpeiCredentials]):
    credentials_cls = SpeiCredentials


class SpeiPaymentSystemController(
    PaymentSystemController[SpeiClient, SpeiSandBoxClient]
):
    client_cls = SpeiSandBoxClient
    sandbox_client_cls = SpeiSandBoxClient

    def _run_deposit(self, trx_id: int, client: T_SandboxClient | T_Client) -> None:  # type: ignore
        self.create_callback(
            trx_id=trx_id,
            callback_type=CallbackType.DEPOSIT_RECEIVED,
        )

    def validate_transaction_attrs(
        self, attrs: dict[str, Any], context: dict[str, Any]
    ) -> None:
        if attrs["type"] == TransactionType.DEPOSIT and not context.get(
            "is_internal_creation"
        ):
            raise ValidationError(
                {"type": "Deposit transaction creation is not allowed for this system"}
            )

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        payload = json.loads(cb.body)

        if "cuentaBeneficiario" in payload:
            deposit_account = payload["cuentaBeneficiario"]
            clabe = int(get_clabe_from_deposit_account(deposit_account))
            wallet = Wallet.objects.get(uuid=cb.get_params["wallet_id"])
            spei_account: DepositAccount = DepositAccount.objects.get(
                unique_account_identifier=clabe,
                wallet=wallet,
            )
            customer_id = spei_account.customer_id

            s = DepositTransactionRequestSerializer(
                data=dict(
                    wallet_id=str(wallet.uuid),
                    customer_id=customer_id,
                    type=TransactionType.DEPOSIT,
                    amount=Decimal(str(payload["monto"])),
                    currency="MXN",
                    status=TransactionStatus.SUCCESS,
                ),
                context={
                    "merchant": wallet.merchant,
                    "is_internal_creation": True,
                },
            )
            if not s.is_valid():
                raise RuntimeError(s.errors)

            trx = s.create(s.validated_data)

            return RemoteTransactionStatus(
                operation_status=TransactionStatus.SUCCESS,
                id_in_payment_system=payload["claveRastreo"],
                raw_data=payload,
                transaction_id=trx.id,
                remote_amount=trx.money,
            )

        else:
            raise NotImplementedError("later")

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        return True


class SpeiAccountSerializer(BaseAccountSerializer):
    def get_deposit_account(self, obj: DepositAccount) -> str:
        return _get_deposit_account_for_clabe(
            obj.unique_account_identifier, obj.extra["mask"]
        )

    def get_unique_together_validators(self) -> list[UniqueTogetherValidator]:
        return []

    def create(self, validated_data: Any) -> DepositAccount:
        wallet_id = validated_data.pop("wallet_id")
        wallet: Wallet = Wallet.objects.get(
            uuid=wallet_id,
            merchant_id=self.context["merchant"].id,
        )
        mask = wallet.credentials["mask"]
        customer_id = validated_data["customer_id"]

        assert "{clabe}" in mask
        actual_length = len(mask.replace("{clabe}", ""))
        expected_length = 17 - 5
        assert actual_length == expected_length, (actual_length, expected_length, mask)

        max_val = 100000

        with transaction.atomic():
            # Select max value from DB
            max_clabe = (
                DepositAccount.objects.filter(
                    wallet=wallet,
                ).aggregate(
                    max=models.Max(
                        Cast(
                            "unique_account_identifier",
                            models.IntegerField(),
                        )
                    )
                )["max"]
                or 0
            )
            clabe = max_clabe + 1
            if clabe >= max_val:
                raise RuntimeError("Could not create CLABE")

            account, created = DepositAccount.objects.select_for_update(
                of=("self",)
            ).get_or_create(
                wallet=wallet,
                customer_id=customer_id,
                defaults=dict(
                    unique_account_identifier=clabe,
                    extra={
                        "mask": mask,
                        "clabe": clabe,
                    },
                ),
            )

        return account


spei_controller = SpeiPaymentSystemController(
    payment_system=const.PaymentSystemType.SPEI,
    default_credentials={
        "mask": "",
    },
)
