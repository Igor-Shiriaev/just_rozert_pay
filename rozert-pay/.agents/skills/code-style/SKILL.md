---
name: cqode-style
globs:
  - "rozert_pay/**/*.py"
  - "tests/**/*.py"
description: Использовать для изменений Python/Django-кода в rozert-pay, где нужно соблюдать проектный стиль, fail-fast-поведение, правила логирования и именования.
---

# Стиль Django Payment Кода

Используй этот навык для задач реализации или ревью Python/Django-кода. Это исчерпывающий справочник по стилю проекта.

Для задач по моделям дополнительно применять `.agents/skills/django-model-rules/SKILL.md`.

## Когда НЕ использовать

- Чисто текстовые правки (документация, конфиги).
- Изменения только в `front/`, `swagger.*`, helm-секретах.

## Порядок работы

### 1. Архитектура слоёв

Бизнес-логика живёт **только** в `services`-слое. Остальные слои — тонкие.

```python
# GOOD — логика в services
class DepositView(APIView):
    def post(self, request):
        result = deposit_service.create_deposit(request.data)
        return Response(result)

# BAD — логика в view
class DepositView(APIView):
    def post(self, request):
        trx = PaymentTransaction.objects.create(...)
        trx.status = "pending"
        trx.save()
        schedule_check.delay(trx.id)
        return Response(...)
```

### 2. Именование

Функции — глаголами, сущности — существительными:

```python
# GOOD
def build_notify_url() -> str: ...
def validate_remote_transaction_status(trx: PaymentTransaction) -> Error | None: ...
def calculate_signature(payload: dict[str, Any], api_key: str) -> str: ...
def is_customer_in_list(customer: Customer, list_type: ListType) -> bool: ...
users_count = len(users)

# BAD
def url() -> str: ...            # не глагол
def check(trx) -> ...: ...      # слишком общее
def process(data): ...           # что именно process?
user_array = [...]               # венгерская нотация
empt = True                      # неочевидное сокращение
```

Правила:

- Имена должны быть самодостаточными — по имени понятно, *что это* или *какой результат даёт функция*, без чтения окружающего кода.
- Функции — глаголами (`build_*`, `validate_*`, `calculate_*`), сущности — существительными.
- Предикаты: `is_*`, `has_*`, `can_*`.
- Коллекции: множественное число (`users`, `errors`), счётчики: `*_count`.
- Не использовать слишком общие имена (`data`, `value`, `process`, `file`) — давать предметные (`filepath`, `domain_name`, `user_email`).
- Пары антонимов согласованно: `old/new`, `before/after`, `start/end`. Не делать «полупары» вроде `value` и `new_value`.
- Не кодировать тип в имени (венгерская нотация): `user_array`, `name_string` — нет.
- Сокращать только общепринятое: `id`, `url`, `num`, `trx`. Не `empt`, `hid`, `txn`.
- Без транслитерации; имена на английском.
- Без односимвольных переменных (`a`, `x`) в рабочем коде.

### 3. Явный доступ к атрибутам

```python
# GOOD — явный доступ
if user_data.phone:
    customer.phone_encrypted = user_data.phone

# BAD — динамический доступ в прикладном коде
status = getattr(trx, "status", None)
setattr(trx, "status", "failed")
```

`getattr`/`setattr` допустимы **только** в инфраструктурном коде (thread-local, dynamic HTTP dispatch, data migrations).

Предпочитать явные ветки условий, чтобы поведение было читаемым и проверяемым статически:

```python
# GOOD — явная ветка
if trx.type == TransactionType.DEPOSIT:
    handle_deposit(trx)
elif trx.type == TransactionType.WITHDRAWAL:
    handle_withdrawal(trx)

# BAD — динамический dispatch в прикладном коде
handler = getattr(self, f"handle_{trx.type}")
handler(trx)
```

### 4. Логирование

```python
# GOOD — модульный логгер + структурированные extra
logger = logging.getLogger(__name__)

logger.info(
    "Processing transaction: Found active limits",
    extra={
        "transaction_id": trx.id,
        "active_limits_count": len(active_limits),
        "customer_id": trx.customer_id,
        "wallet_id": trx.wallet_id,
    },
)

# BAD — print, без extra, утечка данных, f-string, интерполяция строк
print(f"Error: {e}")
logger.info("Got callback")  # нет идентификаторов
logger.info(f"Card: {card_number}")  # PAN в логах
logger.error(f"Error: {e}")
logger.error("Error: %s", e)
```

Правила:

- `logger = logging.getLogger(__name__)` на уровне модуля.
- Ключевые идентификаторы в `extra`: `transaction_id`, `callback_id`, `request_id`, `system`, `status_code`, `wallet_id`.
- `logger.exception(...)` в `except`-блоках, `logger.warning(...)` для деградации, `logger.error(...)` для ошибочного итога.
- **Никогда**: секреты, CVV, полный PAN, токены, приватные ключи, сырые персональные данные.
- Внешние API: логировать метод, URL, статус, длительность. Полные тела — только санитизированно.

### 5. Fail-fast и обработка исключений

```python
# GOOD — guard clause, ранний выход
def validate_remote_transaction_status(
    transaction: PaymentTransaction,
    remote_status: RemoteStatus,
) -> Error | None:
    if not transaction:
        raise ValueError("Transaction is not provided")
    if transaction.status != TransactionStatus.SUCCESS:
        return errors.Error(
            f"received chargeback for non-success transaction {transaction.status}"
        )

# BAD — немое проглатывание
try:
    process_callback(data)
except Exception:
    pass  # потеряли ошибку
```

Правила:

- При невалидном состоянии — завершать явной ошибкой (guard clauses).
- Исключения перехватывать **только** для: добавления контекста, маппинга в доменную ошибку, rollback/cleanup.
- Инфраструктурные вызовы — с явными таймаутами и ограниченными ретраями.
- При отсутствии безопасного recovery — пробрасывать дальше.

### 6. Импорты

```python
# GOOD — абсолютный импорт
from rozert_pay.payment.services import db_services, event_logs
from rozert_pay.risk_lists.services.manager import add_customer_to_blacklist_by_trx

# BAD — относительный импорт
from ..risk_lists.services import checker
```

### 7. Проектные паттерны

- Внешние HTTP-интеграции: использовать `get_external_api_session(trx_id=..., timeout=...)` — обеспечивает event log и метрики.
- Бизнес-критичные service-функции: декоратор `@track_duration("<scope>.<function>")`.
- Пользовательские строки: на английском (ASCII-friendly).
- `@property` — только для дешёвых вычислений или доступа к загруженным данным. Запросы к БД — явными методами (`get_*`).

## Жесткие ограничения

- Без немого проглатывания исключений (`except ...: pass` в прикладном коде).
- Без `getattr`/`setattr`/`hasattr`/`delattr` в прикладном коде без инфраструктурного обоснования.
- Без сырых чувствительных данных в логах (PAN, CVV, токены, ключи).
- Без бизнес-логики в views/serializers/admin — только в `services`.
