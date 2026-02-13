from django.db import models

from rozert_pay.common.models import BaseDjangoModel


# Create your models here.
class CustomerLimit(BaseDjangoModel):
    customer = models.ForeignKey(
        "payment.Customer",
        on_delete=models.CASCADE,
        related_name="client_limits",
        verbose_name="Client",
        null=False,
        blank=False,
    )
