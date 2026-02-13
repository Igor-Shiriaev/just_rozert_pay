from django.db import models


class LimitScope(models.TextChoices):
    RISK = "merchant", "Merchant"
    WALLET = "wallet", "Merchant Wallet"
