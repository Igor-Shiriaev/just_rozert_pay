from django.db import models


class LimitCategory(models.TextChoices):
    RISK = "risk", "Risk"
    GLOBAL_RISK
    BUSINESS = "business", "Business"
