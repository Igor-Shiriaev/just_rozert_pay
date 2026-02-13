from django.db import models


class FeatureFlagName(models.TextChoices):
    RISK_CONTROL_ENABLED = "risk_control_enabled", "Risk control"
