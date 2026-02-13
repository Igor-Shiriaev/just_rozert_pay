from datetime import timedelta
from typing import Any

from auditlog.models import AuditlogHistoryField
from auditlog.registry import auditlog
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from rozert_pay.risk_lists.const import (
    ALLOWED_MATCH_FIELDS,
    ListType,
    MatchFieldKey,
    OperationType,
    ParticipationType,
    ValidFor,
)

VALID_FOR_DELTA: dict[ValidFor, timedelta] = {
    ValidFor.H24: timedelta(hours=24),
    ValidFor.H168: timedelta(hours=168),
    ValidFor.H720: timedelta(hours=720),
}


class RiskListEntry(models.Model):
    """
    A unified class for all list types,
    featuring a single validation method and one query table.
    We use proxy classes to manage different permissions and admin sections.
    """

    list_type = models.CharField(
        verbose_name=_("List Type"),
        max_length=16,
        choices=ListType.choices,
        db_index=True,
    )
    customer = models.ForeignKey(
        "payment.Customer",
        verbose_name=_("Customer"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text=_("The customer to whom this entry applies."),
    )

    scope = models.CharField(max_length=10,
        choices=ParticipationType.choices,
    )
    wallet = models.ForeignKey(
        "payment.Wallet",
        verbose_name=_("Wallet"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text=_("Link to a wallet, if participation type is Wallet."),
    )
    merchant = models.ForeignKey(
        "payment.Merchant",
        verbose_name=_("Merchant"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text=_("Link to a merchant, if participation type is Merchant."),
    )

    created_at = models.DateTimeField(verbose_name=_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name=_("Updated At"), auto_now=True)
    valid_for = models.CharField(
        verbose_name=_("Valid For"), max_length=10, choices=ValidFor.choices
    )
    expires_at = models.DateTimeField(
        verbose_name=_("Expires At"), null=True, blank=True, db_index=True
    )
    reason = models.TextField(_("Reason"), blank=True)
    added_by = models.ForeignKey(
        # NOTE: null if added by the system
        settings.AUTH_USER_MODEL,
        verbose_name=_("Added By"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    operation_type = models.CharField(
        verbose_name=_("Operation Type"),
        max_length=10,
        choices=OperationType.choices,
        default=OperationType.ALL,
    )

    customer_name = models.CharField(
        verbose_name=_("Customer Name"), max_length=255, null=True, blank=True
    )
    customer_wallet_id = models.CharField(
        verbose_name=_("Customer Wallet ID"), max_length=255, null=True, blank=True
    )
    masked_pan = models.CharField(
        verbose_name=_("Masked PAN"), max_length=19, null=True, blank=True
    )
    email = models.EmailField(
        verbose_name=_("Email"), max_length=254, null=True, blank=True
    )
    phone = models.CharField(
        verbose_name=_("Phone"), max_length=255, null=True, blank=True
    )
    ip = models.GenericIPAddressField(
        verbose_name=_("IP Address"), null=True, blank=True
    )
    provider_code = models.CharField(
        verbose_name=_("Provider Code"), max_length=50, null=True, blank=True
    )
    match_fields: list[MatchFieldKey] = ArrayField(  # type: ignore[assignment]
        base_field=models.CharField(
            max_length=30,
            choices=[(f.value, f.value) for f in ALLOWED_MATCH_FIELDS],
        ),
        default=list,
        blank=True,
        help_text=_(
            "Fields actually used for matching."
            "(if all are selected, only non-empty values are stored). If empty, the entry will not match."
        ),
    )
    is_deleted = models.BooleanField(default=False, db_index=True)
    delete_reason = models.TextField(
        verbose_name=_("Deletion Reason"), blank=True, null=True
    )
    history = AuditlogHistoryField(delete_related=True)

    class Meta:
        verbose_name = _("Risk List Entry")
        verbose_name_plural = _("Risk List Entries")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        target = self.customer if self.customer else "Global"
        return f"{self.get_list_type_display()} entry for {target}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.pk:
            if self.list_type == ListType.WHITE and not self.valid_for:
                self.valid_for = ValidFor.H24
            elif self.list_type == ListType.GRAY and not self.valid_for:
                self.valid_for = ValidFor.PERMANENT

        if self.list_type == ListType.BLACK:
            self.valid_for = ValidFor.PERMANENT
        elif self.list_type == ListType.MERCHANT_BLACK:
            self.valid_for = ValidFor.PERMANENT
            self.scope = ParticipationType.MERCHANT

        self.set_expiration()
        super().save(*args, **kwargs)

    def soft_delete(self, *, reason: str) -> None:
        if not reason:
            raise ValueError(gettext("Deletion reason is required for soft delete."))
        self.is_deleted = True
        self.delete_reason = reason
        super().save(update_fields=["is_deleted", "delete_reason", "updated_at"])

    def delete(
        self,
        using: Any | None = None,
        keep_parents: bool = False,
        reason: str | None = None,
    ) -> tuple[int, dict[str, int]]:
        self.soft_delete(reason=reason or "")
        return 1, {self._meta.label: 1}

    def set_expiration(self) -> None:
        if self.valid_for == ValidFor.PERMANENT:
            self.expires_at = None
        else:
            delta = VALID_FOR_DELTA.get(ValidFor(self.valid_for))
            if delta is None:
                raise ValidationError(_("Unknown valid_for value."))
            base_dt = self.created_at or timezone.now()
            self.expires_at = base_dt + delta

    def clean(self) -> None:
        super().clean()
        errors: dict[str, list[Any]] = {}

        if self.scope == ParticipationType.GLOBAL:
            if self.merchant:
                errors.setdefault("merchant", []).append(
                    _("For GLOBAL participation, 'merchant' must be empty.")
                )
            if self.wallet:
                errors.setdefault("wallet", []).append(
                    _("For GLOBAL participation, 'wallet' must be empty.")
                )
            if self.customer:
                errors.setdefault("customer", []).append(
                    _("For GLOBAL participation, 'customer' must be empty")
                )

        elif self.scope == ParticipationType.MERCHANT:
            if not self.merchant:
                errors.setdefault("merchant", []).append(
                    _("For MERCHANT participation, 'merchant' must be selected.")
                )
            if self.wallet:
                errors.setdefault("wallet", []).append(
                    _("For MERCHANT participation, 'wallet' must be empty.")
                )
            if not self.customer:
                errors.setdefault("customer", []).append(
                    _("Customer is required for Merchant participation.")
                )

        elif self.scope == ParticipationType.WALLET:
            if not self.wallet:
                errors.setdefault("wallet", []).append(
                    _("For WALLET participation, 'wallet' must be selected.")
                )
            if self.merchant:
                errors.setdefault("merchant", []).append(
                    _("For WALLET participation, 'merchant' must be empty.")
                )
            if not self.customer:
                errors.setdefault("customer", []).append(
                    _("Customer is required for Wallet participation.")
                )

        if self.list_type == ListType.WHITE:
            if self.scope == ParticipationType.GLOBAL:
                errors.setdefault("participation_type", []).append(
                    _("White List entries cannot be Global.")
                )
            if not self.reason:
                errors.setdefault("reason", []).append(
                    _("A reason is mandatory for White List entries.")
                )

        elif self.list_type == ListType.MERCHANT_BLACK:
            if not self.reason:
                errors.setdefault("reason", []).append(
                    _("A reason is mandatory for Merchant Black List entries.")
                )

        elif self.list_type == ListType.BLACK:
            if not self.reason:
                errors.setdefault("reason", []).append(
                    _("A reason is mandatory for Black List entries.")
                )

        if self.scope == ParticipationType.GLOBAL and self.list_type in [
            ListType.BLACK,
            ListType.GRAY,
        ]:
            field_count = len(
                [field for field in ALLOWED_MATCH_FIELDS if getattr(self, field.value)]
            )
            if field_count < 2:
                errors.setdefault("match_fields", []).append(
                    _(
                        "For a Global entry, at least 2 identifying parameters are required."
                    )
                )

        if errors:
            raise ValidationError(errors)


class WhiteListEntry(RiskListEntry):
    class Meta:
        proxy = True
        verbose_name = _("White List Entry")
        verbose_name_plural = _("White List Entries")


class BlackListEntry(RiskListEntry):
    class Meta:
        proxy = True
        verbose_name = _("Black List Entry")
        verbose_name_plural = _("Black List Entries")


class GrayListEntry(RiskListEntry):
    class Meta:
        proxy = True
        verbose_name = _("Gray List Entry")
        verbose_name_plural = _("Gray List Entries")


class MerchantBlackListEntry(RiskListEntry):
    class Meta:
        proxy = True
        verbose_name = _("Merchant Black List Entry")
        verbose_name_plural = _("Merchant Black List Entries")


auditlog.register(WhiteListEntry, serialize_data=True)
auditlog.register(BlackListEntry, serialize_data=True)
auditlog.register(GrayListEntry, serialize_data=True)
auditlog.register(MerchantBlackListEntry, serialize_data=True)
