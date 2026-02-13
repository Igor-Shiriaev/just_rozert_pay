from django.db import models


class MuweSpeiBank(models.Model):
    """
    MUWE SPEI Bank Model

    Stores bank information from MUWE API for mapping bank codes to names.
    Updated daily via Celery task.
    """

    code = models.CharField(
        max_length=10,
        primary_key=True,
        help_text="Bank code (e.g., '40014' for Santander)",
    )
    name = models.CharField(
        max_length=200,
        help_text="Bank name (e.g., 'SANTANDER')",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this bank is currently supported by MUWE",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_muwe_spei_bank"
        verbose_name = "MUWE SPEI Bank"
        verbose_name_plural = "MUWE SPEI Banks"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"
