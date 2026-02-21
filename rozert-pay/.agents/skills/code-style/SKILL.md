---
name: code-style
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
- Строковые литералы — в двойных кавычках (`"hello"`). Одинарные — только внутри f-string или для избежания экранирования.

### 3. Размер кода

- Функция: ориентир — до **70 строк**. Если больше — разбивать на подфункции с осмысленными именами.
- Модуль (файл): ориентир — до **700 строк**. При превышении — выносить логику в подмодули.
- Аргументы функции: стараться не использовать более **5 позиционных**.
- Вложенность: не более **4 уровней** отступов в теле функции. Глубокую вложенность устранять через guard clauses, ранние return и вынос логики в отдельные функции.

```python
# BAD — глубокая вложенность
def process_transactions(transactions: list[PaymentTransaction]) -> list[str]:
    results = []
    for trx in transactions:
        if trx.status == TransactionStatus.PENDING:
            if trx.wallet:
                if trx.wallet.is_active:
                    results.append(handle_pending(trx))
    return results

# GOOD — guard clauses + вынос логики
def process_transactions(transactions: list[PaymentTransaction]) -> list[str]:
    return [
        handle_pending(trx)
        for trx in transactions
        if is_actionable_transaction(trx)
    ]

def is_actionable_transaction(trx: PaymentTransaction) -> bool:
    if trx.status != TransactionStatus.PENDING:
        return False
    if not trx.wallet or not trx.wallet.is_active:
        return False
    return True
```

### 4. Документирование (docstrings)

- Сервисные функции (`services/`) — **всегда** писать короткий docstring, объясняющий *что* делает функция.
- Остальные функции и методы — docstring добавлять по усмотрению, если имя и сигнатура недостаточно объясняют поведение, side-effects или нетривиальный контракт.
- Формат: одна строка в двойных кавычках, без пустых строк внутри. Для сложных случаев допустим многострочный Google-style.
- Не дублировать сигнатуру — не перечислять аргументы, если их назначение очевидно из типов и имён.

```python
# GOOD — сервисная функция
def create_deposit(data: dict[str, Any]) -> PaymentTransaction:
    """Create a new deposit transaction and schedule status check."""
    ...

# GOOD — хелпер, имя и сигнатура достаточны
def build_notify_url(wallet: Wallet) -> str:
    ...

# GOOD — нетривиальный контракт, docstring уместен
def sync_limits_after_chargeback(trx: PaymentTransaction) -> None:
    """Reverse limit counters and freeze customer if threshold exceeded."""
    ...

# BAD — пересказ сигнатуры
def find_user(user_id: int) -> User | None:
    """Find user by user_id and return User or None."""
    ...
```

### 5. Явный доступ к атрибутам

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

### 6. Логирование

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
logger.error(f"Error: {e}")  # f-string вычисляется всегда, даже если уровень отключён
logger.error("Error: %s", e)  # контекст теряется — идентификаторы должны быть в extra
```

Правила:

- `logger = logging.getLogger(__name__)` на уровне модуля.
- Ключевые идентификаторы в `extra`: `transaction_id`, `callback_id`, `request_id`, `system`, `status_code`, `wallet_id`.
- Не использовать f-string и `%s`-интерполяцию в вызовах логгера. f-string вычисляется безусловно (лишняя работа при отключённом уровне), а `%s` размазывает контекст по строке вместо структурированного `extra`. Весь контекст — в `extra={}`.
- `logger.exception(...)` в `except`-блоках, `logger.warning(...)` для деградации, `logger.error(...)` для ошибочного итога.
- **Никогда**: секреты, CVV, полный PAN, токены, приватные ключи, сырые персональные данные.
- Внешние API: логировать метод, URL, статус, длительность. Полные тела — только санитизированно.

### 7. Fail-fast и обработка исключений

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

### 8. Импорты

```python
# GOOD — абсолютный импорт
from rozert_pay.payment.services import db_services, event_logs
from rozert_pay.risk_lists.services.manager import add_customer_to_blacklist_by_trx

# BAD — относительный импорт
from ..risk_lists.services import checker
```

### 9. Типизация (Python 3.11+)

- Типизация должна быть везде, где это возможно.
- Стараться указывать типизацию максимально точно, насколько это уместно, но без фанатизма.
- Использовать нативный синтаксис типов: `X | Y` вместо `Optional[X]`/`Union[X, Y]`.
- Использовать встроенные коллекции `list[...]`, `dict[...]` вместо `List`, `Dict` из `typing`.
- Импорт из `typing` использовать только для того, чего нет в нативном синтаксисе (`Any`, `TypeVar`, `ParamSpec`, `TypedDict`, и т.д.).
- `Callable` в прикладном коде стараться не передавать в виде аргумента.
- При извлечении значений из словаря явно типизировать целевую переменную.

```python
# GOOD
def find_user(id: int) -> User | None: ...
def validate_remote_transaction_status(trx: PaymentTransaction) -> Error | None: ...
def process(items: list[str] | None, mapping: dict[str, int] | None = None) -> list[int] | None: ...
payload: dict[str, Any]
status: str = payload["status"]

# BAD
from typing import Optional, List, Dict
def find_user(id: int) -> Optional[User]: ...
def process(items: List[str], mapping: Dict[str, int]) -> List[int]: ...
payload: Optional[dict[str, Any]] = None  # лучше: dict[str, Any] | None = None
status = payload["status"]
```

### 10. Проектные паттерны

- Внешние HTTP-интеграции: использовать `get_external_api_session(trx_id=..., timeout=...)` — обеспечивает event log и метрики.
- Бизнес-критичные service-функции: декоратор `@track_duration("<scope>.<function>")`.
- Пользовательские строки: на английском (ASCII-friendly).
- `@property` — только для дешёвых вычислений или доступа к загруженным данным. Запросы к БД — явными методами (`get_*`).
- Стараться писать код без вложенных функций.
  Исключения: декораторы и похожий уже существующий код.
- Для `PaymentTransaction.status`: стандартно использовать `sync_remote_status_with_transaction(...)`; исключения (`refund`/`chargeback`/`chargeback reversal`) допустимы только в контролируемых service-сценариях transaction-processing с обязательными balance side-effects и доменным аудитом.

```python
# Внешний HTTP-запрос через ExternalApiSession
session = get_external_api_session(trx_id=trx.id, timeout=10)
response = session.post(url, json=payload)

# Измерение длительности service-функции
@track_duration("limits.get_active_limits")
def get_active_limits() -> list[CustomerLimit | MerchantLimit]:
    ...
```

## Жесткие ограничения

- Без немого проглатывания исключений (`except ...: pass` в прикладном коде).
- Без `getattr`/`setattr`/`hasattr`/`delattr` в прикладном коде без инфраструктурного обоснования.
- Без `dataclass`/`dataclasses` в проектном коде. Вместо них используй pydantic.BaseModel.
- Без сырых чувствительных данных в логах (PAN, CVV, токены, ключи).
- Без бизнес-логики в views/serializers/admin — только в `services`.
