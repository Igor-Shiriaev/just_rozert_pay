from typing import TYPE_CHECKING
from bm import payment as shared_payment_const
from django.db import models
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.payment.models import PaymentCardBank, PaymentTransaction


if TYPE_CHECKING:
    from rozert_pay.payment.models import PaymentCardBank

class BitsoTransactionExtraData(BaseDjangoModel):
    transaction = models.OneToOneField(PaymentTransaction, on_delete=models.CASCADE)
    clave_rastreo = models.CharField(
        max_length=64, db_index=True, verbose_name="Clave de rastreo"
    )


class BitsoSpeiCardBank(BaseDjangoModel):
    # NOTE: Keep in mind that we have the same model in Betmaster
    COUNTRY_CHOICES = shared_payment_const.COUNTRY_CHOICES

    code = models.CharField(max_length=10, unique=True, verbose_name="Bank Code")
    name = models.CharField(max_length=300, verbose_name="Bank Name")
    country_code = models.CharField(
        max_length=2, choices=COUNTRY_CHOICES, verbose_name="Country Code"
    )
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    banks: models.ManyToManyField["PaymentCardBank"] = models.ManyToManyField(
        "PaymentCardBank", related_name="bitso_banks", blank=True
    )

    def __str__(self) -> str:
        return f"{self.id} {self.name} ({self.code})"  # pragma: no cover

    class Meta:
        verbose_name = "Bitso SPEI Bank"
        verbose_name_plural = "Bitso SPEI Banks"
        ordering = ("code",)
