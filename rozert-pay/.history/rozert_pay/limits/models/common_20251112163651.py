from django.db import models


class LimitScope(models.TextChoices):
    RISK = "risk", "Risk"
    BUSINESS = "business", "Business"
