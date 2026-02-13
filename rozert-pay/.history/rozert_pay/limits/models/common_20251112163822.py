from django.db import models


class LimitCategory(models.TextChoices):
    RISK = "risk", "Risk"
    BUSINESS = "business", "Business"
