import datetime
import json
import re
import typing as ty
import uuid
from datetime import timedelta
from decimal import Decimal
from ipaddress import IPv4Address
from typing import Literal, Optional, Union

from bm import payment as shared_payment_const
from bm.datatypes import Money
from bm.django_utils.encrypted_field import EncryptedFieldType, SecretValue
from bm.utils import BMJsonEncoder
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import QuerySet, Value
from django.db.models.functions import Upper
from django.utils.functional import cached_property
from rozert_pay.common import const, fields
from rozert_pay.common.encryption import (
    DeterministicHashField,
    EncryptedField,
    EncryptedFieldV2,
    KeySetId,
)
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.payment import entities, types
from rozert_pay.payment.factories import get_payment_system_controller

from .entities import UserData
from .permissions import CommonUserPermissions, PaymentPermissions
from .systems.bitso_spei.bitso_spei_const import BITSO_CLAVE_RASTREO_FIELD

BITSO_SPEI_PAYOUT_LOOKUP_INDEX_NAME = "payment_trx_bitso_spei_lookup_idx"


class MerchantGroup(BaseDjangoModel):
    name = models.CharField(max_length=200, unique=True)
    user = models.OneToOneField("account.User", on_delete=models.CASCADE)
    queue = models.CharField(
        max_length=200,
        choices=const.CeleryQueue.choices,
        default=const.CeleryQueue.NORMAL_PRIORITY,
    )

    def __str__(self) -> str:
        return f"MG: {self.name} #{self.id}"


class Merchant(BaseDjangoModel):
    id: types.MerchantID  # type: ignore[assignment]

    uuid = models.UUIDField(unique=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, unique=True)
    merchant_group = models.ForeignKey("MerchantGroup", on_delete=models.CASCADE)
    secret_key = models.CharField(max_length=200, unique=True)
    # NOTE: DELETE?
    risk_control = models.BooleanField(
        default=False,
        help_text="If True, Risk Limits will be checked for this merchant",
    )

    sandbox = models.BooleanField(default=False)

    login_users = models.ManyToManyField(
        "account.User",
        related_name="merchants",
        help_text="Users, who can login to this merchant's dashboard",
    )  # type: ignore[var-annotated]

    operational_status = models.CharField(
        max_length=20,
        choices=const.MerchantOperationalStatus.choices,
        default=const.MerchantOperationalStatus.ACTIVE,
    )
    risk_status = models.CharField(
        max_length=20,
        choices=const.MerchantRiskStatus.choices,
        default=const.MerchantRiskStatus.WHITE,
    )

    def __str__(self) -> str:
        return f"{self.name} #{self.id}"


class ACLGroup(models.Model):
    name = models.CharField(max_length=200, unique=True)

    groups = models.ManyToManyField("MerchantGroup")  # type: ignore[var-annotated]
    wallets = models.ManyToManyField("Wallet")  # type: ignore[var-annotated]
    users = models.ManyToManyField("account.User")  # type: ignore[var-annotated]
    systems = models.ManyToManyField("PaymentSystem")  # type: ignore[var-annotated]

    all_groups = models.BooleanField(default=False)
    all_wallets = models.BooleanField(default=False)
    all_users = models.BooleanField(default=False)
    all_systems = models.BooleanField(default=False)

    level = models.CharField(
        max_length=20, choices=const.ACLLevel.choices, default=const.ACLLevel.READ
    )


class PaymentSystem(BaseDjangoModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    name = models.CharField(max_length=200, unique=True)
    slug = models.CharField(
        max_length=200,
        unique=True,
        null=True,
        blank=True,
    )  # todo: make non null

    type: const.PaymentSystemType = models.CharField(
        max_length=200, choices=const.PaymentSystemType.choices
    )  # type: ignore[assignment]
    is_active = models.BooleanField(default=True)

    deposit_allowed_ttl_seconds = models.PositiveIntegerField(
        default=2 * 24 * 3600,
        help_text="Time to live for deposit transactions. Initial transactions longer than this will be failed with "
        "decline code 'Too long execution'.",
    )
    withdrawal_allowed_ttl_seconds = models.PositiveIntegerField(
        default=24 * 3600,
        help_text="Time to live for withdrawal transactions. Initial transactions longer than this will be failed with "
        "decline code 'Too long execution'.",
    )
    ip_whitelist = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    ip_whitelist_enabled = models.BooleanField(default=True)

    client_request_timeout = models.FloatField(default=30)
    callback_secret_key = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Secret key for callbacks from payment system",
    )

    def clean(self) -> None:
        super().clean()
        for ip in self.ip_whitelist:
            try:
                IPv4Address(ip)
            except Exception:
                raise ValidationError(f"Invalid IP address: {ip}")

    def __str__(self) -> str:
        return self.name

    def save(
        self,
        *args: ty.Any,
        **kwargs: ty.Any,
    ) -> None:
        if not self.slug:
            self.slug = self.make_slug(self.name)
        return super().save(*args, **kwargs)

    @classmethod
    def make_slug(cls, name: str) -> str:
        return re.sub(r"\W+", "-", name.lower())


class Wallet(BaseDjangoModel):
    id: types.WalletId  # type: ignore[assignment]
    merchant_id: types.MerchantID  # type: ignore[assignment]
    currencywallet_set: QuerySet["CurrencyWallet"]  # type: ignore[assignment]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=200)
    uuid = models.UUIDField(unique=True, default=uuid.uuid4)

    merchant: Merchant = models.ForeignKey("Merchant", on_delete=models.CASCADE)  # type: ignore[assignment]
    system = models.ForeignKey("PaymentSystem", on_delete=models.CASCADE)

    credentials: dict[str, ty.Any] = EncryptedField()

    comment = models.TextField(blank=True, default="")
    logs = models.TextField(blank=True, default="")

    default_callback_url = models.URLField(null=True, blank=True)

    # Sandbox parameters
    sandbox_finalization_delay_seconds = models.PositiveIntegerField(default=60)

    allow_negative_balances = models.BooleanField(default=False)
    risk_control = models.BooleanField(
        default=False,
        help_text="If True, Risk Limits will be checked for this wallet",
    )

    def clean(self) -> None:
        controller = get_payment_system_controller(self.system)
        if not controller:
            raise ValidationError(
                f"Payment system controller not found for system {self.system}"
            )

        if isinstance(self.credentials, str):
            try:
                self.credentials = json.loads(self.credentials)
            except Exception as e:
                raise ValidationError(f"Invalid credentials: {e}")

        if not self.merchant.sandbox:
            controller.client_cls.parse_and_validate_credentials(self.credentials)

    def __str__(self) -> str:
        if self.merchant.sandbox:
            sandbox = "[SANDBOX] "
        else:
            sandbox = ""
        return f"{sandbox}{self.name} #{self.id}"


class CurrencyWallet(BaseDjangoModel):
    """Wallet for specific currency."""

    wallet_id: types.WalletId  # type: ignore[assignment]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    currency = fields.CurrencyField()

    # DEPRECATED FIELDS (to be removed in sc-261341)
    balance = fields.MoneyField(default=0)
    hold_balance = fields.MoneyField(default=0)

    # NEW BALANCE FIELDS
    operational_balance = fields.MoneyField(
        default=0,
        help_text="Total funds, including confirmed and pending.",
    )
    frozen_balance = fields.MoneyField(
        default=0,
        help_text="Part of operational_balance that is temporarily locked.",
    )
    pending_balance = fields.MoneyField(
        default=0,
        help_text="Part of operational_balance that is awaiting settlement from a provider.",
    )

    @property
    def available_balance(self) -> Decimal:
        return self.operational_balance - self.frozen_balance - self.pending_balance

    def __str__(self) -> str:
        return (
            f"{self.currency} Wallet #{self.id} | "
            f"Op: {self.operational_balance:.2f}, "
            f"Fr: {self.frozen_balance:.2f}, "
            f"Pen: {self.pending_balance:.2f}, "
            f"Av: {self.available_balance:.2f}"
        )

    class Meta:
        unique_together = ("wallet", "currency")


class PaymentTransactionManager(models.Manager["PaymentTransaction"]):
    def transactions_for_periodic_status_check(self) -> "QuerySet[PaymentTransaction]":
        return (
            self.filter(
                status=const.TransactionStatus.PENDING,
                check_status_until__isnull=False,
            )
            .select_related("wallet")
            .order_by("created_at")
        )

    def for_system(
        self, system: const.PaymentSystemType
    ) -> "QuerySet[PaymentTransaction]":
        return self.filter(wallet__wallet__system__type=system)


class Customer(BaseDjangoModel):
    class Meta:
        ordering = ("id",)

    uuid = models.UUIDField(unique=True, default=uuid.uuid4)
    external_id: types.ExternalCustomerId = models.CharField(  # type: ignore[assignment]
        max_length=255, unique=True
    )
    language = models.CharField(max_length=10, null=True, blank=True)
    risk_control = models.BooleanField(
        default=False,
        help_text="If True, Risk Limits will be checked for this customer",
    )

    email_encrypted: SecretValue[str | None] | None = EncryptedFieldV2(
        key_set_id=KeySetId.PII,
        null=True,
        blank=True,
        view_permission=CommonUserPermissions.CAN_VIEW_PERSONAL_DATA,
    )
    email_deterministic_hash = DeterministicHashField(
        key_set_id=KeySetId.PII_HASH,
        null=True,
        blank=True,
    )
    phone_encrypted: SecretValue[str | None] | None = EncryptedFieldV2(
        key_set_id=KeySetId.PII,
        null=True,
        blank=True,
        view_permission=CommonUserPermissions.CAN_VIEW_PERSONAL_DATA,
    )
    phone_hash = DeterministicHashField(
        key_set_id=KeySetId.PII_HASH,
        null=True,
        blank=True,
    )
    extra_encrypted: SecretValue[dict | None] | None = EncryptedFieldV2(
        key_set_id=KeySetId.PII,
        # TODO: remove null
        null=True,
        blank=True,
        field_type=EncryptedFieldType.JSON,
        view_permission=CommonUserPermissions.CAN_VIEW_PERSONAL_DATA,
    )

    @cached_property
    def user_data(self) -> UserData:
        extra_data: dict[str, ty.Any] = {}
        if self.extra_encrypted is not None:
            extra_data = self.extra_encrypted.get_secret_value() or {}

        if udh := extra_data.get("user_data_history", []):
            if len(udh) > 0:
                return UserData(**udh[-1])

        ud = UserData()
        if self.email_encrypted is not None:
            ud.email = self.email_encrypted.get_secret_value()
        if self.phone_encrypted is not None:
            ud.phone = self.phone_encrypted.get_secret_value()
        ud.language = self.language

        for key, value in extra_data.get("user_data", {}).items():
            if not value:
                continue
            if getattr(ud, key) is None:
                setattr(ud, key, value)

        if ud.date_of_birth and isinstance(ud.date_of_birth, str):
            ud.date_of_birth = datetime.datetime.strptime(ud.date_of_birth, "%Y-%m-%d")

        return ud

    def save(
        self,
        *args: ty.Any,
        **kwargs: ty.Any,
    ) -> None:
        if self.email_encrypted:
            self.email_deterministic_hash = self.email_encrypted.get_secret_value()
        if self.phone_encrypted:
            self.phone_hash = self.phone_encrypted.get_secret_value()

        super().save(
            *args,
            **kwargs,
        )

    def __str__(self) -> str:
        return f"{self.id} external={self.external_id}"


class CustomerExternalPaymentSystemAccount(BaseDjangoModel):
    """
    Represents external customer account in payment system.
    We can receive money from this accounts, or withdraw money to them.

    Unique by (system_type, unique_account_number)

    """

    customer_id: types.CustomerId  # type: ignore[assignment]
    wallet_id: types.WalletId  # type: ignore[assignment]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["system_type", "wallet", "unique_account_number"],
                name="unique_customer_wallet",
            ),
        ]

    uuid: types.CustomerExternalAccountUuid = models.UUIDField(  # type: ignore[assignment]
        unique=True, default=uuid.uuid4
    )
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    unique_account_number = models.CharField(max_length=255)

    wallet = models.ForeignKey("payment.Wallet", on_delete=models.CASCADE)

    system_type = models.CharField(
        max_length=200, choices=const.PaymentSystemType.choices
    )
    extra: dict[types.CustomerWalletExtraKey, ty.Any] = models.JSONField(  # type: ignore[assignment]
        default=dict, blank=True
    )
    active = models.BooleanField(default=True)


class CustomerDepositInstruction(BaseDjangoModel):
    """
    Represents deposit account we provide to customer for deposits.

    For example, Bitso/STP spei works like that:

    * Merchant provides unique customer identity
    * We create DepositInstruction with specific instructions for deposit. For SPEI it's just account number.
    * Merchant gives this account number to customer
    * Customer deposits money to this account
    * We receive callback from payment system and can identify customer by this account number

    Unique constraints:

     * (system_type, deposit_account_number)
    """

    wallet_id: types.WalletId  # type: ignore[assignment]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["system_type", "deposit_account_number"],
                name="cusdepoins_sys_account_number",
            )
        ]

    system_type = models.CharField(
        max_length=200, choices=const.PaymentSystemType.choices
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
    )

    deposit_account_number = models.CharField(max_length=255, unique=True)
    wallet = models.ForeignKey(
        "payment.Wallet",
        on_delete=models.CASCADE,
    )


class CustomerCard(BaseDjangoModel):
    uuid = models.UUIDField(unique=True, default=uuid.uuid4)
    unique_identity = models.CharField(max_length=200)
    card_data: dict[str, ty.Any] | Literal[""] = EncryptedField()
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)

    @property
    def card_data_entity(self) -> entities.CardData | None:
        if not self.card_data:
            return None
        return entities.CardData(**self.card_data)

    @property
    def masked_card(self) -> str:
        ce = self.card_data_entity
        assert ce
        return f"{ce.card_num.get_secret_value()[:8]}***{ce.card_num.get_secret_value()[-4:]}"

    def __str__(self) -> str:
        return f"{self.masked_card} cus={self.customer_id} #{self.id}"

    class Meta:
        unique_together = ("unique_identity", "customer")


class PaymentTransaction(BaseDjangoModel):
    id: types.TransactionId  # type: ignore[assignment]
    wallet_id: types.CurrencyWalletId
    customer_id: types.CustomerId

    class Meta:
        permissions = [
            (
                PaymentPermissions.CAN_ACTUALIZE_TRANSACTION,
                "Can actualize payment transaction",
            ),
            (
                PaymentPermissions.CAN_SET_TRANSACTION_STATUS,
                "Can set transaction status",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["system_type", "id_in_payment_system"],
                name="unique_transaction_id_in_payment_system",
            ),
        ]
        indexes = [
            models.Index(
                Upper(
                    models.Func(
                        models.F("extra"),
                        Value("claveRastreo"),
                        function="jsonb_extract_path_text",
                    )
                ),
                "amount",
                name=BITSO_SPEI_PAYOUT_LOOKUP_INDEX_NAME,
                condition=models.Q(
                    system_type=const.PaymentSystemType.BITSO_SPEI,
                    type=const.TransactionType.WITHDRAWAL,
                    extra__has_key=BITSO_CLAVE_RASTREO_FIELD,
                ),
            ),
        ]

    objects: PaymentTransactionManager = PaymentTransactionManager()  # type: ignore[assignment]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    uuid = models.UUIDField(unique=True, default=uuid.uuid4)

    wallet = models.ForeignKey(CurrencyWallet, on_delete=models.CASCADE)
    system_type: const.PaymentSystemType = models.CharField(
        max_length=200, choices=const.PaymentSystemType.choices
    )  # type: ignore[assignment]

    status = models.CharField(
        max_length=255,
        choices=const.TransactionStatus.choices,
        default=const.TransactionStatus.PENDING,
    )

    amount = models.DecimalField(max_digits=15, decimal_places=2)
    amount2 = fields.MoneyField(null=True, blank=True)  # type: ignore[misc]

    type = models.CharField(max_length=20, choices=const.TransactionType.choices)
    currency = fields.CurrencyField()
    currency2 = fields.CurrencyField(null=True, blank=True)  # type: ignore[misc]

    callback_url = models.URLField(null=True, blank=True)
    # TODO: add to API
    redirect_url = models.URLField(null=True, blank=True)

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    customer_external_account = models.ForeignKey(
        CustomerExternalPaymentSystemAccount,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    customer_card = models.ForeignKey(
        CustomerCard,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    customer_instruction = models.ForeignKey(
        CustomerDepositInstruction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    id_in_payment_system = models.CharField(
        max_length=200, null=True, blank=True, db_index=True
    )

    decline_code = models.CharField(max_length=200, null=True, blank=True)
    decline_reason = models.CharField(max_length=200, null=True, blank=True)

    instruction = models.JSONField(null=True, blank=True)
    extra = models.JSONField(blank=True, default=dict)

    check_status_until = models.DateTimeField(null=True, blank=True)

    # Account of the user in the payment system
    external_account_id = models.CharField(max_length=200, null=True, blank=True)

    @property
    def is_deposit(self) -> bool:
        return self.type == const.TransactionType.DEPOSIT

    @property
    def is_withdrawal(self) -> bool:
        return self.type == const.TransactionType.WITHDRAWAL

    @cached_property
    def system(self) -> PaymentSystem:
        return self.wallet.wallet.system

    @property
    def uuid_short(self) -> str:
        return str(self.uuid).split("-")[0]

    @cached_property
    def ttl(self) -> timedelta:
        if self.type == const.TransactionType.DEPOSIT:
            return timedelta(seconds=self.system.deposit_allowed_ttl_seconds)
        elif self.type == const.TransactionType.WITHDRAWAL:
            return timedelta(
                seconds=self.system.withdrawal_allowed_ttl_seconds
            )  # 1 day
        raise RuntimeError

    @cached_property
    def is_sandbox(self) -> bool:
        return self.wallet.wallet.merchant.sandbox

    @cached_property
    def user_data(self) -> Optional[entities.UserData]:
        if ud := self.extra.get("user_data"):
            return entities.UserData(**ud)

        if self.customer:
            return self.customer.user_data

        return None  # pragma: no cover

    @property
    def form(self) -> Optional[entities.TransactionExtraFormData]:
        if data := self.extra.get("form"):
            return entities.TransactionExtraFormData(**data)
        return None

    @form.setter
    def form(self, value: entities.TransactionExtraFormData) -> None:
        self.extra["form"] = value.to_dict()

    @property
    def withdraw_to_account(self) -> Optional[str]:
        # TODO: delete
        return self.extra.get("withdraw_to_account")

    @property
    def money(self) -> Money:
        return Money(self.amount, self.currency)

    def save_extra(self) -> None:
        self.save(update_fields=["extra", "updated_at"])

    def save(self, *args: ty.Any, **kwargs: ty.Any) -> None:
        update_fields = kwargs.get("update_fields")
        updated_fields: set[str] = set()

        if self.amount2 is None:
            self.amount2 = self.amount
            updated_fields.add("amount2")
        if self.currency2 is None:
            self.currency2 = self.currency
            updated_fields.add("currency2")

        if update_fields is not None and updated_fields:
            kwargs["update_fields"] = set(update_fields) | updated_fields

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        uuid_short = str(self.uuid)[:8]
        created = self.created_at.strftime("%m.%d %H:%M")
        return f"{self.type} {self.system_type}: {self.amount} {self.currency} {self.status} #{self.id} ({uuid_short} {created})"


class TransactionManager(PaymentTransaction):
    """
    Proxy model for the Transaction Manager view.
    """

    class Meta:
        proxy = True
        verbose_name = "Transaction Manager"
        verbose_name_plural = "Transaction Manager"


class PaymentTransactionEventLog(BaseDjangoModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    transaction = models.ForeignKey(PaymentTransaction, on_delete=models.CASCADE)
    incoming_callback = models.ForeignKey(
        "IncomingCallback", on_delete=models.CASCADE, null=True, blank=True
    )
    event_type = models.CharField(max_length=255, choices=const.EventType.choices)
    description = models.TextField(null=True, blank=True)
    extra = models.JSONField(default=dict, encoder=BMJsonEncoder)
    request_id = models.CharField(max_length=200, null=True, blank=True)


class EventLog(BaseDjangoModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    event_type = models.CharField(max_length=255, choices=const.EventType.choices)
    description = models.TextField(null=True, blank=True)
    extra = models.JSONField(default=dict, encoder=BMJsonEncoder)
    request_id = models.CharField(max_length=200, null=True, blank=True)
    merchant = models.ForeignKey(
        "Merchant", on_delete=models.CASCADE, null=True, blank=True
    )
    system_type = models.CharField(
        max_length=200, choices=const.PaymentSystemType.choices
    )
    customer = models.ForeignKey(
        "Customer", on_delete=models.CASCADE, null=True, blank=True
    )


class OutcomingCallback(BaseDjangoModel):
    def get_transaction_id(self) -> types.TransactionId:
        return ty.cast(types.TransactionId, self.transaction_id)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    transaction = models.ForeignKey(PaymentTransaction, on_delete=models.CASCADE)
    callback_type = models.CharField(max_length=255, choices=const.CallbackType.choices)
    target = models.URLField()

    body = models.JSONField()
    status = models.CharField(
        max_length=20,
        choices=const.CallbackStatus.choices,
        default=const.CallbackStatus.PENDING,
    )
    error = models.TextField(null=True, blank=True)
    logs = models.TextField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    max_attempts = models.PositiveIntegerField(default=10)
    current_attempt = models.PositiveIntegerField(default=0)


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, obj):  # type: ignore[no-untyped-def]
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class IncomingCallback(BaseDjangoModel):
    def get_transaction_id(self) -> types.TransactionId:
        return ty.cast(types.TransactionId, self.transaction_id)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    system = models.ForeignKey(PaymentSystem, on_delete=models.CASCADE)
    transaction = models.ForeignKey(
        PaymentTransaction, on_delete=models.CASCADE, null=True, blank=True
    )
    body = models.TextField()
    headers = models.JSONField(blank=True, default=dict)
    get_params = models.JSONField(blank=True)
    ip = models.GenericIPAddressField()
    status = models.CharField(
        max_length=20,
        choices=const.CallbackStatus.choices,
        default=const.CallbackStatus.PENDING,
    )
    error_type = models.CharField(
        max_length=255,
        choices=const.IncomingCallbackError.choices,
        null=True,
        blank=True,
    )
    error = models.TextField(null=True, blank=True)
    traceback = models.TextField(null=True, blank=True)
    remote_transaction_status = models.JSONField(
        default=dict, encoder=CustomJsonEncoder
    )


class DepositAccount(BaseDjangoModel):
    """
    Declares accounts for deposits for customers,
    for payment systems without deposit instantiation on our side.

    Typical flow:

    * Merchant created deposit account passing customer_id
    * API returns deposit account for that customer
    * Merchant gives deposit account to customer
    * Customer makes deposit to that account
    * API receives callback from payment system
    * API creates PaymenTransaction and sends callback to merchant
    """

    created_at = models.DateTimeField(auto_now_add=True)

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    customer_id = models.CharField(max_length=100)

    unique_account_identifier = models.CharField(max_length=100)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["wallet", "customer_id"],
                name="unique_customer_id_per_merchant",
            ),
            models.UniqueConstraint(
                fields=["wallet", "unique_account_identifier"],
                name="unique_account_identifier",
            ),
        ]


class Bank(models.Model):
    # NOTE: Keep in mind that we have the same model in Betmaster
    id = models.AutoField(primary_key=True)

    name = models.CharField(max_length=300)
    is_non_bank = models.BooleanField(
        default=False, verbose_name="Other licensed financial institution"
    )

    def __str__(self) -> str:
        return self.name  # pragma: no cover

    class Meta:
        verbose_name = "Bank"
        ordering = ("name",)


def validate_bin(value: int) -> None:
    if len(str(value)) not in [6, 8]:  # pragma: no cover
        raise ValidationError("Invalid BIN format")  # pragma: no cover


class PaymentCardBank(models.Model):
    # NOTE: Keep in mind that we have the same model in Betmaster
    COUNTRY_CHOICES = shared_payment_const.COUNTRY_CHOICES
    CARD_TYPE_CHOICES = shared_payment_const.CARD_TYPE_CHOICES
    bank_id: int

    id = models.AutoField(primary_key=True)
    bin = models.IntegerField(
        unique=True,
        verbose_name="BIN",
        validators=[validate_bin],
    )
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, related_name="bins")
    card_type = models.PositiveSmallIntegerField(
        choices=shared_payment_const.CARD_TYPE_CHOICES, default=0
    )
    card_class = models.TextField(
        choices=shared_payment_const.CardClass.choices, null=True
    )
    is_virtual = models.BooleanField(default=False, verbose_name="Virtual Card")
    is_prepaid = models.BooleanField(default=False, verbose_name="Prepaid Card")
    raw_category = models.TextField(
        null=True,
        blank=True,
        verbose_name="Raw Category",
        help_text="Raw from XML file",
    )
    country = models.CharField(max_length=10, choices=COUNTRY_CHOICES)
    remark = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def find_by_bin(cls, card_bin: Union[int, str]) -> Optional["PaymentCardBank"]:
        card_bin = str(card_bin)
        if len(card_bin) > 6:
            card_bank_by_bin = {
                str(bank.bin): bank
                for bank in cls.objects.select_related("bank").filter(
                    bin__in=[card_bin, card_bin[:6]]
                )
            }
            card_bank = card_bank_by_bin.get(card_bin)
            if not card_bank:
                card_bank = card_bank_by_bin.get(card_bin[:6])
        else:
            card_bank = cls.objects.select_related("bank").filter(bin=card_bin).first()
        return card_bank

    def __str__(self):  # type: ignore
        return f"{self.bin} {self.bank} ({self.country})"  # pragma: no cover

    class Meta:
        verbose_name = "BIN"
        ordering = ("bin",)


from .systems.spei_stp import spei_stp_models  # type: ignore[no-redef]  # noqa
