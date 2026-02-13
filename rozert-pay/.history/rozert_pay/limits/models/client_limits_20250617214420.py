from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import TextChoices
from rozert_pay.common.models import BaseDjangoModel


class ClientLimitPeriod(TextChoices):
    DAY = "day"
    HOUR = "hour"


class CustomerLimit(BaseDjangoModel):
    customer = models.ForeignKey(
        "payment.Customer",
        on_delete=models.CASCADE,
        related_name="client_limits",
        verbose_name="Клиент",
    )
    active = models.BooleanField(
        default=True, help_text="Статус лимита, включен или выключен"
    )
    description = models.TextField(
        blank=True, help_text="Описание лимита заданное пользователем"
    )

    period = models.CharField(max_length=255, choices=ClientLimitPeriod.choices)

    max_successful_operations = models.PositiveIntegerField(
        verbose_name="Максимальное количество успешных операций за период",
        null=True,
        blank=True,
    )

    max_failed_operations = models.PositiveIntegerField(
        verbose_name="Максимальное количество неуспешных операций за период",
        null=True,
        blank=True,
    )

    min_operation_amount = models.DecimalField(
        verbose_name="Минимальная сумма одной операции",
        help_text="Минимальная сумма, разрешенная для одной операции",
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        null=True,
        blank=True,
    )

    max_operation_amount = models.DecimalField(
        verbose_name="Максимальная сумма одной операции",
        help_text="Максимальная сумма, разрешенная для одной операции",
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        null=True,
        blank=True,
    )

    total_successful_amount = models.DecimalField(
        verbose_name="Общая сумма успешных операций за период",
        help_text="Максимальная общая сумма всех успешных операций за указанный период",
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        null=True,
        blank=True,
    )

    decline_on_exceed = models.BooleanField(
        verbose_name="Отклонять при превышении",
        help_text="Включает отклонение операции при превышении лимита",
        default=False,
    )

    is_critical = models.BooleanField(
        verbose_name="Критический лимит",
        help_text="Переводит алерт в категорию критических уведомлений",
        default=False,
    )

    def clean(self) -> None:
        super().clean()
