from django.db import models

class LimitScope(models.TextChoices):
    MERCHANT = "merchant", "Merchant"
    WALLET = "wallet", "Merchant Wallet"