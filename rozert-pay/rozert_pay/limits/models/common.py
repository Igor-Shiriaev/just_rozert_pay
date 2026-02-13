from django.db import models


class LimitCategory(models.TextChoices):
    RISK = "risk", "Risk"
    GLOBAL_RISK = "global_risk", "Global Risk"
    BUSINESS = "business", "Business"
