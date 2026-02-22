---
name: python-class-rules
globs:
  - "rozert_pay/**/*.py"
description: "Использовать для задач, где добавляются или меняются Python/Django-классы в rozert-pay: admin-классы, service/base-классы, контроллеры, клиенты и DTO."
---

# Правила Написания Классов В rozert-pay

Используй этот навык, когда в задаче создаются или меняются классы.
Общие правила именования, логирования, fail-fast и ограничения (без `getattr`/`dataclass`, и т.д.) — в `.agents/skills/code-style/SKILL.md`.
Правила тестовых классов — в `.agents/skills/django-testing/SKILL.md`.

## Когда НЕ использовать

- Если задача про Django-модели: использовать `.agents/skills/django-model-rules/SKILL.md`.
- Изменения только в функциях без новых/изменяемых классов.
- Чисто документарные правки.

## 1. Сначала выбрать правильный тип класса

- `Admin`/`Form` — только для представления и валидации в Django admin.
- `Service class` — когда нужна stateful-оркестрация из нескольких шагов.
- `Client`/`Controller` — для внешних платежных систем (интеграционный слой).
- `DTO` — по умолчанию `pydantic.BaseModel`; `TypedDict` — см. секцию 8.

Если состояние не требуется, предпочитай функцию, а не класс.

## 2. Структура класса

Порядок внутри класса:

1. Class attributes / конфигурация.
2. `__init__` с минимальной инициализацией.
3. Dunder-методы (`__str__`, `__repr__`, `__call__`, и т.д.).
4. `@cached_property` / `@property`.
5. Публичные методы API.
6. Protected hooks (`_run_*`, `_parse_*`, `_get_*`).
7. Приватные helper-методы.

```python
# GOOD — скелет base-класса по проектному стандарту
class BasePaymentClient(ty.Generic[T_Credentials]):
    # 1. class attributes
    credentials_cls: ty.Type[T_Credentials]

    # 2. __init__
    def __init__(self, trx_id: int, timeout: float = 10) -> None:
        self.trx_id = trx_id
        self.session = ExternalApiSession(
            on_request=PaymentTransactionEventLogOnRequest(trx_id),
            on_response=PaymentTransactionEventLogOnResponse(trx_id),
            timeout=timeout,
        )
        self._post_init()

    # 4. cached_property — ленивый доступ к тяжёлым данным
    @cached_property
    def trx(self) -> PaymentTransaction:
        return db_services.get_transaction(trx_id=self.trx_id, for_update=False)

    # 5. публичный API — @final для стабильного контракта
    @final
    def get_transaction_status(self) -> RemoteTransactionStatus | errors.Error:
        try:
            return self._get_transaction_status()
        except Exception as e:
            logger.exception("Error getting transaction status")
            return errors.Error(f"Error getting transaction status: {e}")

    # 6. protected hooks — наследники реализуют
    def _get_transaction_status(self) -> RemoteTransactionStatus:
        raise NotImplementedError

    def _post_init(self) -> None:
        pass
```

Ориентиры:

- `rozert_pay/payment/services/base_classes.py` (`BasePaymentClient`)
- `rozert_pay/payment/services/transaction_actualization.py` (`BaseTransactionActualizer`)
- `rozert_pay/payment/services/transaction_set_status.py` (`BaseTransactionSetter`)

## 3. Base-классы и наследование

- Базовые классы именовать `Base*`.
- В base-классе — стабильный публичный API и инварианты.
- Вариативную логику выносить в protected hooks, которые реализуют наследники.
- Для обязательных hooks — `raise NotImplementedError` (проектный стандарт).
  `abc.ABC` + `@abstractmethod` **не использовать** для единообразия.
  (В `base_controller.py` есть исключение: `@abc.abstractmethod` без наследования от `ABC` — не воспроизводить в новом коде.)
- Для методов, которые нельзя переопределять, — `@final`.
- Если метод работает только с class-level конфигурацией, — `@classmethod`.

```python
# GOOD — base-класс с @final API и protected hooks
class BaseTransactionSetter(ty.Generic[T]):
    form_cls: type[T]

    @final
    def set_status(self, trx: PaymentTransaction) -> Error | None:
        form = self.get_form(trx)
        if not form.is_valid():
            return Error(form.errors)
        self.save_form(form)
        return None

    def get_form(self, trx: PaymentTransaction) -> T:
        raise NotImplementedError

    def save_form(self, form: T) -> None:
        raise NotImplementedError


# GOOD — наследник реализует только hooks
class DefaultTransactionSetter(BaseTransactionSetter[StatusForm]):
    form_cls = StatusForm

    def get_form(self, trx: PaymentTransaction) -> StatusForm:
        return StatusForm(instance=trx, data=self._build_form_data(trx))

    def save_form(self, form: StatusForm) -> None:
        form.save()
```

## 4. Generic type parameters

Параметризовать класс через `ty.Generic[T]`, когда base-класс работает с типом, который варьируется у наследников (credentials, form, client).

- `TypeVar` объявлять в `types.py` или в начале модуля с base-классом.
- Имя: `T_` + предметная сущность (`T_Credentials`, `T_Client`). Однобуквенные `T` — только для локальных/вспомогательных случаев (`T = TypeVar("T", bound=SetTransactionForm)`).
- `bound` — указывать всегда, когда есть базовый тип.

```python
# rozert_pay/payment/types.py — общие TypeVar для payment-иерархий
T_Credentials = ty.TypeVar("T_Credentials", bound=pydantic.BaseModel)
T_Client = ty.TypeVar("T_Client", bound="base_classes.BasePaymentClient")

# Использование в base-классе
class BasePaymentClient(ty.Generic[T_Credentials]):
    credentials_cls: ty.Type[T_Credentials]

# Наследник фиксирует тип
class StpCodiClient(BasePaymentClient[StpCodiCredentials]):
    credentials_cls = StpCodiCredentials
```

## 5. Composition vs Inheritance

В проекте используются оба подхода. Правило выбора:

- **Наследование** — для контрактов и переиспользования кода в иерархиях одного типа (все платёжные клиенты — `BasePaymentClient`, все контроллеры — `PaymentSystemController`).
- **Композиция** — для runtime-зависимостей между разными типами. Передавать зависимости через `__init__`, параметры функций или class attributes.

```python
# GOOD — композиция: controller принимает зависимости через class attrs и __init__
class PaymentSystemController(Generic[T_Client, T_SandboxClient]):
    client_cls: Type[T_Client]
    sandbox_client_cls: Type[T_SandboxClient]

    def __init__(
        self,
        *,
        payment_system: const.PaymentSystemType,
        transaction_actualizer_cls: type[BaseTransactionActualizer[Any]] = DEFAULT_ACTUALIZER_CLS,
        transaction_setter_cls: type[BaseTransactionSetter[Any]] = DEFAULT_TRANSACTION_SETTER,
    ) -> None:
        self.payment_system = payment_system
        self.transaction_actualizer_cls = transaction_actualizer_cls
        self.transaction_setter_cls = transaction_setter_cls

    def get_client(self, trx: PaymentTransaction) -> T_Client:
        return self.client_cls(trx_id=trx.id)


# GOOD — композиция через параметр функции
def initiate_deposit(
    client: _Client,
    trx_id: types.TransactionId,
    *,
    controller: PaymentSystemController[Any, Any],
) -> ...:
    response = client.deposit()
    ...


# BAD — наследование ради передачи зависимости
class DepositService(PaymentSystemController):  # не связаны по типу
    ...
```

Не строить глубокие иерархии наследования, когда хватает инъекции зависимости.

## 6. Состояние и побочные эффекты

- В `__init__` только сохранить параметры и собрать лёгкие зависимости.
- DB/HTTP операции — в явных методах, а не в конструкторе.
- Для ленивого доступа к данным — `@cached_property` (пример: `BasePaymentClient.trx` в секции 2).
- `@property` — только для дешёвых вычислений / доступа к уже загруженным данным.

```python
# BAD — запрос к БД в __init__
class PaymentClient:
    def __init__(self, trx_id: int) -> None:
        self.trx = PaymentTransaction.objects.get(id=trx_id)  # DB в конструкторе
        self.wallet = self.trx.wallet.wallet                  # ещё DB-запрос
```

## 7. Admin-классы

- Admin-класс остаётся тонким, без бизнес-логики.
- Конфигурацию держать в class attrs (`list_display`, `list_filter`, `readonly_fields` и т.д.).
- Общие части выносить в base/mixin-классы.

Ориентиры:

- `rozert_pay/limits/admin/base.py`
- `rozert_pay/limits/admin/customer_limits.py`
- `rozert_pay/limits/admin/merchant_limits.py`

## 8. DTO и классы-контракты

- По умолчанию использовать `pydantic.BaseModel` для DTO и классов-контрактов.
- Для внешних callback payload можно разрешать лишние поля через `ConfigDict(extra="allow")`.
- `TypedDict` допустим **только** когда выполнены оба условия:
  1. Обрабатывается batch **от ~5 000 сущностей** и выше.
  2. Профилирование показало, что валидация `BaseModel` даёт заметный overhead.

  Во всех остальных случаях — `BaseModel`.

Ориентиры:

- `rozert_pay/limits/services/limits.py` (`TypedDict` — batch-сценарий)
- `rozert_pay/payment/systems/bitso_spei/bitso_spei_controller.py` (`BaseModel` payload)

## 9. Protocol (structural subtyping)

`Protocol` используется в проекте для lightweight-интерфейсов, когда нужен только контракт без наследования.

Применять `Protocol`, когда:

- Функция принимает объект, от которого нужен только один-два метода/атрибута.
- Не нужно наследование и shared-реализация.

Не применять, когда:

- Есть shared-реализация — использовать base-класс с `raise NotImplementedError`.
- Класс уже часть иерархии наследования.

Именование: `_`-префикс, определять рядом с функцией-потребителем (не выносить в отдельный модуль).

```python
# GOOD — Protocol для duck-typed параметра
class _Client(ty.Protocol):
    def deposit(self) -> entities.PaymentClientDepositResponse: ...


def initiate_deposit(client: _Client, trx_id: types.TransactionId) -> ...:
    response = client.deposit()
    ...


# GOOD — Protocol для атрибутного контракта
class _TAccount(ty.Protocol):
    wallet_account: str
    customer_uuid: UUID
```

## 10. Dunder-методы

- `__str__` — реализовать, только если дефолт (`MyEntity object (42)`) недостаточно информативен (подробнее — в `django-model-rules`). Для service/DTO-классов — не требуется.
- `__repr__` — не определять; используются дефолты Django и pydantic. Добавлять только при отладочной необходимости.
- `__eq__` / `__hash__` — не переопределять без явной потребности. Django-модели сравниваются по PK, pydantic — по полям.
- `__slots__` — не использовать. Django-модели и pydantic несовместимы с `__slots__`.
- `__call__` — для callable-объектов: декораторы, callback-хендлеры.

```python
# GOOD — callable callback handler
class PaymentTransactionEventLogOnRequest:
    def __init__(self, trx_id: int) -> None:
        self.trx_id = trx_id

    def __call__(self, request: dict[str, Any]) -> str:
        return event_logs.create_outgoing_event_log(self.trx_id, request)
```

Порядок dunder-методов в классе (PEP 8):
`__init__` → `__str__` → `__repr__` → `__eq__` / `__hash__` → `__call__` → `__enter__` / `__exit__`.

## 11. `assert` vs явные исключения

- `assert` — для инвариантов, которые «невозможны» при корректной логике (dev-time safety net). Может быть отключён через `-O`.
- Явные исключения (`ValueError`, `Error`, guard clauses) — для бизнес-валидации и проверки входных данных.

```python
# GOOD — assert для структурного инварианта (dev-time)
assert issubclass(
    self.sandbox_client_cls, self.client_cls
), f"{self.sandbox_client_cls} must be subclass of {self.client_cls}"

# GOOD — явное исключение для входных данных
def validate_remote_transaction_status(
    transaction: PaymentTransaction | None,
    remote_status: RemoteTransactionStatus,
) -> CleanRemoteTransactionStatus | Error:
    if not transaction:
        raise ValueError("Transaction is not provided")
    if not remote_status.decline_code:
        return Error("Decline code is not provided for failed final status")
```

## 12. Чего избегать

- Классы «на будущее» без фактического состояния/поведения.
- Тяжёлые действия в `__init__` (DB lock, внешний HTTP).
- Смешивание доменной логики с transport/UI-слоем (views/admin/serializers).
- Остальные ограничения (без `getattr`, без `dataclass`, и т.д.) — в `.agents/skills/code-style/SKILL.md`, секция «Жёсткие ограничения».

## 13. Чеклист перед завершением

- Выбран правильный тип класса для задачи.
- Публичный API и hooks разделены.
- Абстрактные методы — через `raise NotImplementedError`, без `abc.ABC`.
- Generic type parameters — `TypeVar` с `bound`, имя `T_` + сущность.
- Зависимости между разными типами — через композицию, а не наследование.
- Нет бизнес-логики в admin/views/serializers.
- Для новых/изменённых моделей применены правила из `.agents/skills/django-model-rules/SKILL.md`.
- Для тестов на изменённые классы применены правила из `.agents/skills/django-testing/SKILL.md`.
