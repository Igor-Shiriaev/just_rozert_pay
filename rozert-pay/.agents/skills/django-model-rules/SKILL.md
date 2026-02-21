---
name: django-model-rules
globs:
  - "rozert_pay/**/models.py"
  - "rozert_pay/**/models/**/*.py"
  - "rozert_pay/**/migrations/**/*.py"
  - "rozert_pay/**/admin.py"
description: Использовать для задач, где добавляются или изменяются Django-модели, их инварианты, транзакционные обновления, миграции и связанные правила консистентности в rozert-pay.
---

# Правила Работы С Django-Моделями

Используй этот навык, когда задача затрагивает модели, их поля, инварианты, конкурентный доступ, миграции или обновления платежных сущностей.

Общие стилевые и архитектурные правила — в `AGENTS.md` (секции 5-6). Здесь только правила, специфичные для моделей.

## Когда НЕ использовать

- Изменения только в `services`/`views`/`serializers` без затрагивания моделей.
- Чисто текстовые правки (документация, комментарии).

## Порядок работы

### 1. Определить scope изменений

Найти затронутые модели и связанные сервисы. Основные модели: `rozert_pay/payment/models.py`, `rozert_pay/balances/models.py`, `rozert_pay/limits/models/`.

### 2. Проверить базовые соглашения по модели

Новая модель **должна** соответствовать паттерну:

```python
# GOOD
class MyEntity(BaseDjangoModel):              # наследовать BaseDjangoModel
    uuid = models.UUIDField(unique=True, default=uuid.uuid4)  # публичный id
    status = models.CharField(
        max_length=32, choices=MyStatus.choices,  # статусы через TextChoices
    )
    amount = fields.MoneyField(default=0)      # деньги через MoneyField
    merchant = models.ForeignKey(
        Merchant, on_delete=models.PROTECT,     # PROTECT для финансовых FK
    )
    history = AuditlogHistoryField(delete_related=True)  # аудит

    class Meta:
        ...

auditlog.register(MyEntity, serialize_data=True)


# BAD — нарушает сразу несколько правил
class MyEntity(models.Model):                  # не BaseDjangoModel
    amount = models.FloatField()               # не MoneyField
    merchant = models.ForeignKey(
        Merchant, on_delete=models.CASCADE,     # CASCADE для финансовой сущности
    )
```

Чеклист:

- `BaseDjangoModel` по умолчанию (даёт `id`, `created_at`, `updated_at`).
- Внешний идентификатор — отдельное `uuid`-поле с `unique=True, default=uuid.uuid4`.
- Статусы/типы — через `TextChoices` (пример: `common/const.py` → `TransactionStatus`, `TransactionType`).
- Денежные значения — через `fields.MoneyField`, **не** `DecimalField`/`FloatField`.
- Аудит — `AuditlogHistoryField` в модели + `auditlog.register(...)` в конце файла.
- PII — существующие паттерны шифрования/хеширования.
- `__str__` — реализовать, только если значение по умолчанию (`MyEntity object (42)`) недостаточно информативно. Возвращать краткую идентифицирующую строку (например, `f"MyEntity({self.uuid})"`).
- Необязательные параметры полей (`related_name`, `verbose_name`, `help_text`/описания и т.п.) указывать только при реальной необходимости.

### 3. Проверить правила целостности

- `on_delete`: для FK на финансовые/исторические сущности — `PROTECT`. **Не ослаблять** до `CASCADE`/`SET_NULL` без явного обоснования.
- Инварианты модели валидировать в `clean()`. `clean()` не вызывается автоматически при `save()` — если нужно провалидировать инстанс вне `full_clean()`, вызывать `instance.clean()` явно.

#### DB Constraints

Бизнес-инварианты, которые СУБД может проверить, дублировать на уровне БД:

```python
# GOOD — инвариант защищён на уровне БД
class CurrencyWallet(BaseDjangoModel):
    operational_balance = fields.MoneyField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(operational_balance__gte=0),
                name="%(app_label)s_%(class)s_positive_operational_balance",
            ),
        ]

# GOOD — условная уникальность
class MerchantLimit(BaseDjangoModel):
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT)
    limit_type = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "limit_type"],
                condition=models.Q(is_active=True),
                name="%(app_label)s_%(class)s_unique_active_limit",
            ),
        ]
```

- Числовые инварианты (баланс >= 0, сумма > 0) — `CheckConstraint`.
- Условная уникальность (один активный лимит на мерчанта) — `UniqueConstraint` с `condition`.
- `unique_together` допустим для безусловной уникальности, но предпочитать `UniqueConstraint` для единообразия.

### 4. Проверить правила обновлений и конкурентности

```python
# GOOD — атомарная блокировка + частичное обновление
with transaction.atomic():
    wallet = CurrencyWallet.objects.select_for_update().get(pk=wallet_id)
    wallet.operational_balance += amount
    wallet.save(update_fields=["operational_balance", "updated_at"])

# BAD — нет блокировки, полный save
wallet = CurrencyWallet.objects.get(pk=wallet_id)
wallet.operational_balance += amount
wallet.save()  # перезаписывает все поля, гонка при конкурентном доступе
```

```python
# GOOD — точечное обновление ключа + save_extra()
trx.extra[TransactionExtraFields.REDIRECT_RECEIVED_DATA] = request.data
trx.save_extra()  # PaymentTransaction.save_extra() -> save(update_fields=["extra", "updated_at"])

# BAD — ручной save(update_fields=...) вместо save_extra()
trx.extra[TransactionExtraFields.REDIRECT_RECEIVED_DATA] = request.data
trx.save(update_fields=["extra", "updated_at"])

# BAD — перезаписывает весь extra без блокировки
trx.extra = {"redirect_data": request.data}
trx.save()
```

Чеклист:

- Финансовые обновления: `transaction.atomic()` + `select_for_update()`.
- Частичные изменения: всегда `save(update_fields=[...])`, не голый `save()`.
- JSON `extra`: точечно менять ключи (`trx.extra[key] = value`) и сохранять через `trx.save_extra()`, не перезаписывать весь dict.
- Фоновые задачи: запускать через `transaction.on_commit(...)` / `execute_on_commit(...)`.
- Правила по статусам и HTTP — см. `AGENTS.md`, секция 5.

### 5. Паттерны запросов

#### N+1

```python
# GOOD — один запрос вместо N+1
transactions = PaymentTransaction.objects.select_related(
    "wallet", "wallet__merchant",
).filter(status=TransactionStatus.PENDING)

for trx in transactions:
    process(trx.wallet.merchant.name)  # данные уже загружены

# BAD — N+1: 2 дополнительных запроса на каждую итерацию
for trx in PaymentTransaction.objects.filter(status=TransactionStatus.PENDING):
    process(trx.wallet.merchant.name)
```

- `select_related` — для FK / OneToOne (JOIN).
- `prefetch_related` — для M2M / reverse FK (отдельный запрос + Python-join).

#### Custom Managers / QuerySets

- Повторяющиеся цепочки `.filter(...).select_for_update()` — выносить в метод менеджера или QuerySet.
- Менеджеры **не** содержат бизнес-логику — только инкапсуляция запросов.

```python
# GOOD — повторяющийся паттерн вынесен в менеджер
class CurrencyWalletQuerySet(models.QuerySet):
    def locked(self) -> "CurrencyWalletQuerySet":
        return self.select_for_update()

    def for_merchant(self, merchant_id: int) -> "CurrencyWalletQuerySet":
        return self.filter(wallet__merchant_id=merchant_id)

class CurrencyWallet(BaseDjangoModel):
    objects = CurrencyWalletQuerySet.as_manager()

# Использование
with transaction.atomic():
    wallet = CurrencyWallet.objects.locked().get(pk=wallet_id)
```

### 6. Правила миграций

При изменении моделей проверить миграцию на безопасность:

- **Добавление nullable-поля**: безопасно — `AddField` с `null=True`.
- **Добавление non-null поля**: в два шага — сначала `AddField(null=True)` + backfill, потом `AlterField(null=False)`.
- **Удаление поля**: сначала убрать все обращения к полю в коде, потом удалить поле в следующей миграции.
- **Rename поля**: `RenameField` безопасен, но проверить все queryset/serializer/admin ссылки.
- **Добавление индекса на большую таблицу**: использовать `AddIndex` с `CREATE INDEX CONCURRENTLY` (через `migrations.RunSQL` или `AddIndexConcurrently` из `django.contrib.postgres`).
- Всегда запускать `make makemigrations` и проверять сгенерированный файл перед коммитом.
- Если миграция потенциально может сделать долгий лок, то ЯВНО написать про это в отчёте.

#### Пример: добавление non-null поля в два шага

```python
# Миграция 1 — добавить nullable + backfill
from django.db import migrations, models


def backfill_risk_score(apps, schema_editor):
    Wallet = apps.get_model("payment", "Wallet")
    # Для больших таблиц использовать батч-обновление (chunks по 1000-5000 строк),
    # чтобы не держать долгий лок на всю таблицу.
    Wallet.objects.filter(risk_score__isnull=True).update(risk_score=0)


class Migration(migrations.Migration):
    dependencies = [("payment", "0041_previous")]

    operations = [
        migrations.AddField(
            model_name="wallet",
            name="risk_score",
            field=models.IntegerField(null=True),
        ),
        migrations.RunPython(backfill_risk_score, migrations.RunPython.noop),
    ]
```

```python
# Миграция 2 — убрать null (отдельный деплой)
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payment", "0042_add_risk_score")]

    operations = [
        migrations.AlterField(
            model_name="wallet",
            name="risk_score",
            field=models.IntegerField(default=0),
        ),
    ]
```

### 7. Индексы

- Поля, по которым идёт фильтрация в queryset — добавлять `db_index=True`, если селективность достаточно высокая.
- Уникальные пары — через `unique_together` или `UniqueConstraint`.
- JSON-поля с частыми lookups — рассмотреть `GIN`-индекс.

### 8. Финализация

- Обновить admin-конфигурацию, если менялись модели (поля в `list_display`, `list_filter`, `search_fields`).
- Запустить `make mypy` и таргетные тесты.

## Жесткие ограничения

- Без массовых обновлений исторических ledger-записей.
- Без `FloatField`/`DecimalField` для денег — только `MoneyField`.
- Без `on_delete=CASCADE` на FK к финансовым/историческим сущностям без явного обоснования.
- Без `IntegerChoices` для статусов/типов — только `TextChoices`.
- Без голого `save()` на финансовых моделях — всегда `save(update_fields=[...])`.
