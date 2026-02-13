from enum import StrEnum


class FeatureFlagName(models.TextChoices):
    RISK_CONTROL_ENABLED = "risk_control_enabled"
