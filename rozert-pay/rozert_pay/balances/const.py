from django.db import models
from django.utils.translation import gettext_lazy as _


class BalanceTransactionType(models.TextChoices):
    """
    Defines the business reason for a balance change.
    """

    # --- Standard Operations ---
    OPERATION_CONFIRMED = (
        "OPERATION_CONFIRMED",
        _("Successful deposit. Increases operational and pending balances."),
    )
    FEE = "FEE", _("Fee charged for a service. Decreases operational balance.")

    # --- Settlement Flow ---
    SETTLEMENT_REQUEST = (
        "SETTLEMENT_REQUEST",
        _("Merchant requested a payout. Moves funds from available to frozen."),
    )
    SETTLEMENT_CANCEL = (
        "SETTLEMENT_CANCEL",
        _("Payout request was cancelled. Moves funds from frozen back to available."),
    )
    SETTLEMENT_CONFIRMED = (
        "SETTLEMENT_CONFIRMED",
        _(
            "Payout was successfully processed. Decreases operational and frozen balances."
        ),
    )
    SETTLEMENT_FROM_PROVIDER = (
        "SETTLEMENT_FROM_PROVIDER",
        _(
            "Funds physically received from a payment provider. Decreases pending balance, making funds available."
        ),
    )
    SETTLEMENT_REVERSAL = (
        "SETTLEMENT_REVERSAL",
        _(
            "A previously successful payout was returned. Increases operational balance."
        ),
    )
    # --- Dispute & Risk ---
    CHARGE_BACK = (
        "CHARGEBACK",
        _("A chargeback was received. Decreases operational balance."),
    )
    ROLLING_RESERVE_HOLD = (
        "ROLLING_RESERVE_HOLD",
        _("Funds held for rolling reserve. Moves funds from available to frozen."),
    )
    ROLLING_RESERVE_RELEASE = (
        "ROLLING_RESERVE_RELEASE",
        _("Rolling reserve period expired. Moves funds from frozen back to available."),
    )

    # --- Manual Interventions ---
    FROZEN = (
        "FROZEN",
        _(
            "Manual freeze of funds by an operator. Moves funds from available to frozen."
        ),
    )
    UNFROZEN = (
        "UNFROZEN",
        _(
            "Manual unfreeze of funds by an operator. Moves funds from frozen back to available."
        ),
    )
    MANUAL_ADJUSTMENT = (
        "MANUAL_ADJUSTMENT",
        _("Manual balance correction by an operator. Affects operational balance."),
    )

    # --- System & Migration ---
    INITIAL_MIGRATION = (
        "INITIAL_MIGRATION",
        _("Initial balance state created during data migration."),
    )


class InitiatorType(models.TextChoices):
    SYSTEM = "SYSTEM", _("System")
    USER = "USER", _("User")
    SERVICE = "SERVICE", _("Internal Service")


class ReserveStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("Active")
    RELEASED = "RELEASED", _("Released")
