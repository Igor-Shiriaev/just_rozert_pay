import uuid
from decimal import Decimal
from typing import Any

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from rozert_pay.common import fields

from .const import BalanceTransactionType, InitiatorType, ReserveStatus


class BalanceTransaction(models.Model):
    """
    Represents a single, atomic change to a CurrencyWallet's balances.
    This model is the source of truth for all balance audits. Each record
    is an immutable ledger entry.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    currency_wallet = models.ForeignKey(
        "payment.CurrencyWallet",
        on_delete=models.PROTECT,
        related_name="balance_transactions",
    )
    type = models.CharField(
        max_length=50, choices=BalanceTransactionType.choices, db_index=True
    )

    # Amount is signed: positive for credits (IN), negative for debits (OUT).
    # This simplifies balance aggregation via SUM().
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    amount2 = fields.MoneyField(null=True, blank=True)  # type: ignore[misc]

    # Balance snapshots for full auditability
    operational_before = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text=_(
            "The total funds (including pending and frozen) before the operation."
        ),
    )
    operational_before2 = fields.MoneyField(  # type: ignore[misc]
        null=True,
        blank=True,
        help_text=_(
            "The total funds (including pending and frozen) before the operation."
        ),
    )
    operational_after = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text=_("The total funds after the operation."),
    )
    operational_after2 = fields.MoneyField(  # type: ignore[misc]
        null=True,
        blank=True,
        help_text=_("The total funds after the operation."),
    )
    frozen_before = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text=_(
            "The portion of operational funds that was frozen before the operation."
        ),
    )
    frozen_before2 = fields.MoneyField(  # type: ignore[misc]
        null=True,
        blank=True,
        help_text=_(
            "The portion of operational funds that was frozen before the operation."
        ),
    )
    frozen_after = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text=_(
            "The portion of operational funds that is frozen after the operation."
        ),
    )
    frozen_after2 = fields.MoneyField(  # type: ignore[misc]
        null=True,
        blank=True,
        help_text=_(
            "The portion of operational funds that is frozen after the operation."
        ),
    )
    pending_before = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text=_(
            "The portion of operational funds awaiting settlement before the operation."
        ),
    )
    pending_before2 = fields.MoneyField(  # type: ignore[misc]
        null=True,
        blank=True,
        help_text=_(
            "The portion of operational funds awaiting settlement before the operation."
        ),
    )
    pending_after = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text=_(
            "The portion of operational funds awaiting settlement after the operation."
        ),
    )
    pending_after2 = fields.MoneyField(  # type: ignore[misc]
        null=True,
        blank=True,
        help_text=_(
            "The portion of operational funds awaiting settlement after the operation."
        ),
    )

    payment_transaction = models.ForeignKey(
        "payment.PaymentTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
    )
    description = models.TextField(null=True, blank=True)
    initiator = models.CharField(
        max_length=50, choices=InitiatorType.choices, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        updated_fields: set[str] = set()

        if self.amount2 is None:
            self.amount2 = self.amount
            updated_fields.add("amount2")
        if self.operational_before2 is None:
            self.operational_before2 = self.operational_before
            updated_fields.add("operational_before2")
        if self.operational_after2 is None:
            self.operational_after2 = self.operational_after
            updated_fields.add("operational_after2")
        if self.frozen_before2 is None:
            self.frozen_before2 = self.frozen_before
            updated_fields.add("frozen_before2")
        if self.frozen_after2 is None:
            self.frozen_after2 = self.frozen_after
            updated_fields.add("frozen_after2")
        if self.pending_before2 is None:
            self.pending_before2 = self.pending_before
            updated_fields.add("pending_before2")
        if self.pending_after2 is None:
            self.pending_after2 = self.pending_after
            updated_fields.add("pending_after2")

        if update_fields is not None and updated_fields:
            kwargs["update_fields"] = set(update_fields) | updated_fields

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.type} {self.amount} for Wallet #{self.currency_wallet_id}"

    class Meta:
        ordering = ["-created_at"]


class RollingReserveHold(models.Model):
    """
    Tracks a single, specific hold of funds for the Rolling Reserve risk policy.

    A Rolling Reserve is a risk management strategy where a percentage of a merchant's
    revenue is held for a set period (e.g., 10% for 90 days) to cover potential
    future losses from chargebacks or refunds. This model tracks each individual
    amount held and its expiration date, allowing the system to automatically
    release the funds back to the merchant's available balance once the period is over.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    currency_wallet = models.ForeignKey(
        "payment.CurrencyWallet",
        on_delete=models.PROTECT,
        related_name="rolling_reserve_holds",
    )
    amount = fields.MoneyField(
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    hold_until = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=50,
        choices=ReserveStatus.choices,
        default=ReserveStatus.ACTIVE,
        db_index=True,
    )

    source_transaction = models.ForeignKey(
        BalanceTransaction,
        on_delete=models.PROTECT,
        related_name="created_rolling_reserve",
    )
    release_transaction = models.ForeignKey(
        BalanceTransaction,
        on_delete=models.SET_NULL,
        related_name="released_rolling_reserve",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Hold {self.amount} for Wallet #{self.currency_wallet_id} until {self.hold_until.date()}"

    class Meta:
        ordering = ["-created_at"]
