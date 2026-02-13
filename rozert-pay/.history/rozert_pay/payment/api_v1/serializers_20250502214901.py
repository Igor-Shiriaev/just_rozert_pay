import logging
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rozert_pay.common import const
from rozert_pay.common.const import TransactionType
from rozert_pay.payment.factories import get_payment_system_controller
from rozert_pay.payment.models import DepositAccount, PaymentTransaction, Wallet
from rozert_pay.payment.services import db_services

logger = logging.getLogger(__name__)


class BalanceSerializer(serializers.Serializer):
    currency = serializers.CharField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)


class WalletSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True, source="uuid")
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    balances = serializers.SerializerMethodField()

    @extend_schema_field(field=BalanceSerializer(many=True))
    def get_balances(self, obj: Wallet) -> dict:
        return BalanceSerializer(obj.currencywallet_set.all(), many=True).data


class InstructionSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=const.InstructionType.choices,
        help_text="""
Instruction type:

* **instruction_file** - File should be downloaded from `link` and given to user.
  User makes deposit according to instruction in file.

* **instruction_qr_code** - QR code should be shown to user. QR code in response is base64 encoded.
        """,
    )
    link = serializers.URLField(
        required=False,
    )
    qr_code = serializers.CharField(
        help_text="Base64 encoded QR code",
        required=False,
    )

    def validate(self, attrs: dict) -> dict:
        if attrs["type"] == const.InstructionType.INSTRUCTION_FILE:
            if not attrs.get("link"):
                raise serializers.ValidationError(
                    {"link": _("This field is required.")}
                )
        elif attrs["type"] == const.InstructionType.INSTRUCTION_QR_CODE:
            if not attrs.get("qr_code"):
                raise serializers.ValidationError(
                    {"qr_code": _("This field is required.")}
                )
        else:
            raise serializers.ValidationError({"type": _("Invalid instruction type.")})
        return attrs


class CommonTransactionSerializerMixin:
    validated_data: dict
    context: dict

    def to_representation(self, instance: PaymentTransaction) -> dict:
        ret = super().to_representation(instance)  # type: ignore[misc]
        ret["wallet_id"] = str(instance.wallet.wallet.uuid)
        return ret

    def common_transaction_validation(self, attrs: dict[str, Any]) -> Wallet:
        wallet_id: str = attrs["wallet_id"]
        context_merchant_id: int = self.context["merchant"].id
        amount: Decimal = attrs["amount"]

        wallet = Wallet.objects.select_for_update().filter(uuid=wallet_id).first()
        if not wallet:
            raise serializers.ValidationError({"wallet_id": _("Wallet not found")})

        if wallet.merchant_id != context_merchant_id:
            logger.error(
                "merchant requested wallet he does not own",
                extra={
                    "wallet_id": wallet_id,
                    "merchant_id": context_merchant_id,
                },
            )
            raise serializers.ValidationError({"wallet_id": _("Wallet not found")})

        if amount <= 0:
            raise serializers.ValidationError(
                {"amount": _("Amount must be greater than 0.")}
            )

        return wallet


class DepositTransactionRequestSerializer(  # type: ignore[misc]
    serializers.Serializer, CommonTransactionSerializerMixin
):
    wallet_id = serializers.UUIDField()

    customer_id = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Customer ID. Required for deposits for: SPEI_STP",
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    redirect_url = serializers.URLField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Redirect URL for payment system to redirect user after payment.",
    )
    callback_url = serializers.URLField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Callback url for payment system",
    )

    @transaction.atomic
    def validate(self, attrs: dict) -> dict:
        wallet = self.common_transaction_validation(attrs)

        attrs["type"] = TransactionType.DEPOSIT

        if ps := get_payment_system_controller(wallet.system):
            ps.validate_transaction_attrs(attrs, self.context)

        return attrs

    @transaction.atomic
    def create(self, validated_data: dict) -> PaymentTransaction:
        *_, trx = db_services.create_transaction(
            wallet_id=validated_data["wallet_id"],
            amount=validated_data["amount"],
            currency=validated_data["currency"],
            callback_url=validated_data.get("callback_url"),
            redirect_url=validated_data.get("redirect_url"),
            type=TransactionType.DEPOSIT,
            merchant_id=self.context["merchant"].id,
            user_data=validated_data.get("user_data"),
            withdraw_to_account=None,
            customer_id=validated_data.get("customer_id"),
            extra=self._get_extra(),
        )

        controller = get_payment_system_controller(trx.system)
        assert controller
        controller.on_db_transaction_created_via_api(trx)
        return trx

    def _get_extra(self) -> dict[str, Any]:
        return {}


class WithdrawalTransactionRequestSerializer(  # type: ignore[misc]
    serializers.Serializer, CommonTransactionSerializerMixin
):
    wallet_id = serializers.UUIDField()

    customer_id = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Customer ID. Required for deposits for: SPEI_STP",
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    withdraw_to_account = serializers.CharField()

    @transaction.atomic
    def validate(self, attrs: dict) -> dict:
        wallet = self.common_transaction_validation(attrs)

        current_balance = (
            wallet.currencywallet_set.select_for_update()
            .filter(currency=attrs.get("currency"))
            .aggregate(balance=Sum("balance"))
        )
        if (current_balance["balance"] or 0) < attrs["amount"]:
            print('')
            raise serializers.ValidationError({"amount": _("Insufficient funds.")})

        if ps := get_payment_system_controller(wallet.system):
            ps.validate_transaction_attrs(attrs, self.context)

        return attrs

    @transaction.atomic
    def create(self, validated_data: dict) -> PaymentTransaction:
        _, currency_wallet, trx = db_services.create_transaction(
            wallet_id=validated_data["wallet_id"],
            amount=validated_data["amount"],
            currency=validated_data["currency"],
            callback_url=validated_data.get("callback_url"),
            redirect_url=validated_data.get("redirect_url"),
            type=TransactionType.WITHDRAWAL,
            merchant_id=self.context["merchant"].id,
            user_data=validated_data.get("user_data"),
            withdraw_to_account=validated_data["withdraw_to_account"],
        )

        currency_wallet.balance -= validated_data["amount"]
        currency_wallet.hold_balance += validated_data["amount"]
        if currency_wallet.balance < 0:
            raise serializers.ValidationError("Insufficient balance")
        currency_wallet.save()

        controller = get_payment_system_controller(trx.system)
        assert controller
        controller.on_db_transaction_created_via_api(trx)

        return trx


class UserDataSerializer(serializers.Serializer):
    email = serializers.EmailField()
    phone = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    post_code = serializers.CharField()
    city = serializers.CharField()
    country = serializers.CharField()
    state = serializers.CharField()
    address = serializers.CharField()


class UserDataSerializerMixin(serializers.Serializer):
    user_data = UserDataSerializer()


class FormDataSerializer(serializers.Serializer):
    action_url = serializers.URLField()
    method = serializers.ChoiceField(choices=["get", "post"])
    fields = serializers.DictField()  # type: ignore[assignment]


class TransactionResponseSerializer(serializers.Serializer):
    id = serializers.CharField(source="uuid")

    status = serializers.ChoiceField(choices=const.TransactionStatus.choices)
    decline_code = serializers.CharField()
    decline_reason = serializers.CharField()
    deposit_account = serializers.CharField(
        help_text="Deposit account number. <br>"
        "If presented in response, instruction must be shown to user to make deposit to this account.",
    )
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    instruction = InstructionSerializer(
        required=False,
        allow_null=True,
        help_text=f"Instruction for customer. Required for deposits for: {const.PaymentSystemType.PAYCASH}",
    )
    callback_url = serializers.URLField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Callback URL for payment system to notify about transaction status change.",
    )
    customer_id = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Customer ID. Required for deposits for: SPEI_STP",
    )
    type = serializers.ChoiceField(choices=const.TransactionType.choices)

    currency = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)

    form = FormDataSerializer(
        required=False,
        allow_null=True,
        help_text="Form data for redirecting user to payment system.",
    )
    external_account_id = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="External account of user performed deposit. Payment system specific.",
    )
    user_data = UserDataSerializer(allow_null=True, required=False)

    def to_representation(self, instance: PaymentTransaction) -> dict:
        ret = super().to_representation(instance)
        ret["wallet_id"] = str(instance.wallet.wallet.uuid)
        return ret


class BaseAccountSerializer(serializers.ModelSerializer):
    deposit_account = serializers.SerializerMethodField(
        help_text="Deposit account for customer. "
        "Ask customer to make deposit using this account."
    )
    wallet_id = serializers.UUIDField()

    def to_representation(self, instance: DepositAccount) -> dict:
        ret = super().to_representation(instance)
        ret["wallet_id"] = str(instance.wallet.uuid)
        return ret

    def get_deposit_account(self, obj: DepositAccount) -> str:
        raise NotImplementedError

    class Meta:
        model = DepositAccount
        read_only_fields = (
            "id",
            "created_at",
            "deposit_account",
        )
        fields = (
            *read_only_fields,
            "wallet_id",
            "customer_id",
        )
