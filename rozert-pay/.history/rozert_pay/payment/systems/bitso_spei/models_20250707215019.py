from django.db import models
from bm.constants import COUNTRY_CHOICES as SHARED_PAYMENT_COUNTRY_CHOICES
from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.payment.models import PaymentTransaction


class BitsoTransactionExtraData(BaseDjangoModel):
    transaction = models.OneToOneField(PaymentTransaction, on_delete=models.CASCADE)
    clave_rastreo = models.CharField(
        max_length=64, db_index=True, verbose_name="Clave de rastreo"
    )


class BitsoSpeiCardBank(BaseDjangoModel):
    COUNTRY_CHOICES = SHARED_PAYMENT_COUNTRY_CHOICES

    code = models.CharField(max_length=10, unique=True, verbose_name='Bank Code')
    name = models.CharField(max_length=300, verbose_name='Bank Name')
    country_code = models.CharField(
        max_length=2, choices=COUNTRY_CHOICES, verbose_name='Country Code'
    )
    is_active = models.BooleanField(default=True, verbose_name='Is Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    banks = models.ManyToManyField('PaymentCardBank', related_name='bitso_banks', blank=True)

    def __str__(self) -> str:
        return f'{self.id} {self.name} ({self.code})'

    class Meta:
        verbose_name = 'Bitso SPEI Bank'
        verbose_name_plural = 'Bitso SPEI Banks'
        ordering = ('code',)
