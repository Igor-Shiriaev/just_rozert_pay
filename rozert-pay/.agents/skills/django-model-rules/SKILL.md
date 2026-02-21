---
name: django-model-rules
globs:
  - "rozert_pay/**/models.py"
  - "rozert_pay/**/models/**/*.py"
  - "rozert_pay/**/migrations/**/*.py"
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
- Необязательные параметры полей (`related_name`, `verbose_name`, `help_text`/описания и т.п.) указывать только при реальной необходимости.

### 3. Проверить правила целостности

- `on_delete`: для FK на финансовые/исторические сущности — `PROTECT`. **Не ослаблять** до `CASCADE`/`SET_NULL` без явного обоснования.
- Инварианты валидировать в `clean()`.

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
- Hot-path запросы: `select_related` / `prefetch_related`.
- Фоновые задачи: запускать через `transaction.on_commit(...)` / `execute_on_commit(...)`.
- Правила по статусам и HTTP — см. `AGENTS.md`, секция 5.

### 5. Правила миграций

При изменении моделей проверить миграцию на безопасность:

- **Добавление nullable-поля**: безопасно — `AddField` с `null=True`.
- **Добавление non-null поля**: в два шага — сначала `AddField(null=True)` + backfill, потом `AlterField(null=False)`.
- **Удаление поля**: сначала убрать все обращения к полю в коде, потом удалить поле в следующей миграции.
- **Rename поля**: `RenameField` безопасен, но проверить все queryset/serializer/admin ссылки.
- **Добавление индекса на большую таблицу**: использовать `AddIndex` с `CREATE INDEX CONCURRENTLY` (через `migrations.RunSQL` или `AddIndexConcurrently` из `django.contrib.postgres`).
- Всегда запускать `make makemigrations` и проверять сгенерированный файл перед коммитом.
- Если миграция потенциально может сделать долгий лок, то ЯВНО написать про это в отчёте.

### 6. Индексы

- Поля, по которым идёт фильтрация в queryset — добавлять `db_index=True`, если селективность достаточно высокая.
- Уникальные пары — через `unique_together` или `UniqueConstraint`.
- JSON-поля с частыми lookups — рассмотреть `GIN`-индекс.

### 7. Финализация

- Обновить admin-конфигурацию, если менялись модели (поля в `list_display`, `list_filter`, `search_fields`).
- Запустить `make mypy` и таргетные тесты.

## Жесткие ограничения

- Без массовых обновлений исторических ledger-записей.
- Без прямой смены `PaymentTransaction.status` в произвольном бизнес-коде.
  Допустимое исключение: контролируемые service-сценарии `refund`/`chargeback`/`chargeback reversal` в transaction-processing с обязательными balance side-effects и доменным аудитом.
- Без нарушений транзакционной консистентности в финансовом флоу.
- Без `FloatField`/`DecimalField` для денег — только `MoneyField`.
- Без `on_delete=CASCADE` на FK к финансовым/исторческим сущностям без явного обоснования.
