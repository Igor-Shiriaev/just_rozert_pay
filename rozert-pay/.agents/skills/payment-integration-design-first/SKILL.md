---
name: payment-integration-design-first
globs:
  - "rozert_pay/payment/systems/**/*.py"
  - "docs/integrations/**/*.md"
  - "rozert_pay/common/const.py"
  - "rozert_pay/payment/controller_registry.py"
  - "rozert_pay/payment/api_v1/urls.py"
description: Использовать для новых и изменяемых платежных интеграций. Перед правками кода обязателен подтверждённый дизайн-документ. Покрывает полный цикл — от дизайна до регистрации контроллера.
---

# Проектирование Перед Разработкой Для Платежных Интеграций

Используй этот навык для задач по платежным интеграциям: новый провайдер, изменения флоу, изменения callback/статусов, добавление нового метода (deposit/withdraw).

## Связанные навыки

- Детали по `sync_remote_status_with_transaction`, балансовым side-effects, переходам статусов и callback-флоу: `.agents/skills/payment-transaction-workflow/SKILL.md`.
- Тестирование: `.agents/skills/django-testing/SKILL.md`.
- Доменные сущности (модели, поля, связи): `.agents/skills/domain-entities/SKILL.md`.

## Когда НЕ использовать

- Баг-фиксы внутри существующей интеграции без изменения флоу/статусов.
- Рефакторинг без изменения поведения.
- Изменения только в тестах существующей интеграции.

## Порядок работы

### 1. Изучить контекст

- Изучить документацию провайдера (API, callback-формат, статусы).
- Посмотреть существующие интеграции как образец: `rozert_pay/payment/systems/`.

### 2. Создать/обновить дизайн-документ

Создать `docs/integrations/<integration_name>/design.md`. Обязательные секции:

```markdown
# <Integration Name> Integration Design Document

## Общая информация
- Название интеграции: `<system_name>`
- Платежная система: <Provider>
- Документация: <URL>

## Доступ и креденшалы
- Список полей credentials (хранятся в wallet)
- Секреты только в credentials, не в коде

## Валюты и форматирование
- Поддерживаемые валюты
- Формат сумм (целые числа / Decimal / минорные единицы)
- Минимальная / максимальная сумма (если есть)

## Внешние зависимости
- Сторонние SDK/библиотеки (если есть, например `paymentsds-mpesa`)
- Версия и способ установки
- Что мокировать в тестах (SDK vs HTTP)

## Deposit Flow
- Параметры запроса
- Пошаговый flow (создание → запрос к провайдеру → callback → статус)
- Откуда берётся `id_in_payment_system`

## Withdraw Flow
- Параметры запроса
- Пошаговый flow
- Условия отклонения (например, нет привязанного аккаунта)

## Transaction Status Check
- Как проверять статус через API провайдера
- Маппинг статусов провайдера → TransactionStatus

## Callback обработка
- Формат callback (JSON-поля)
- Валидация подписи (HMAC / RSA / другой алгоритм)
- Если подпись не поддерживается — какие альтернативные меры (IP whitelist, `callback_secret_key`)
- Как искать транзакцию по callback-данным

## Структура интеграции
- Список файлов и их назначение
- Роуты (URL endpoints)
- Путь к тестам

## Привязка внешнего аккаунта (если применимо)
- Используется ли `CustomerExternalPaymentSystemAccount`
- Какой идентификатор хранится (телефон, email, wallet ID)
- Когда создаётся привязка (при deposit / при withdraw / вручную)

## Контекст для будущих итераций
- Ключевые допущения и ограничения
- Особенности реализации
```

Образцы: `docs/integrations/cardpay_applepay/design.md`, `docs/integrations/mpesa_mz/design.md`.

### 3. Утвердить дизайн

- Показать разработчику краткое резюме дизайна с ключевыми решениями.
- **Дождаться явного подтверждения.** Никаких правок кода до утверждения.

### 4. Реализовать интеграцию

Структура файлов новой интеграции:

```
rozert_pay/payment/systems/<system_name>/
├── __init__.py
├── client.py          # наследует BasePaymentClient — deposit(), withdraw(), _get_transaction_status()
├── controller.py      # наследует PaymentSystemController — _run_deposit(), _run_withdraw(), _parse_callback(), _is_callback_signature_valid()
├── views.py           # API endpoints (deposit, withdraw, callback)
├── entities.py        # Pydantic-модели credentials и DTO
├── const.py           # Константы, маппинг статусов
└── helpers.py         # Вспомогательные функции (подпись, парсинг)
```

Для простых интеграций допустим single-file формат (как `paycash.py`).

**Критерии выбора формата:**

| Формат | Когда использовать |
|---|---|
| Single-file | Только deposit (или только withdraw), нет внешнего SDK, нет сложной callback-подписи, ≤ ~300 строк |
| Директория | Оба метода (deposit + withdraw), внешний SDK, сложная логика подписи, или файл превышает ~300 строк |

#### Базовые классы

**Client** — наследовать `BasePaymentClient[T_Credentials]` из `payment/services/base_classes.py`:

```python
class MySystemClient(BasePaymentClient[MySystemCredentials]):
    payment_system_name = PaymentSystemType.MY_SYSTEM
    credentials_cls = MySystemCredentials

    def deposit(self) -> entities.PaymentClientDepositResponse:
        ...

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        ...

    def _get_transaction_status(self) -> RemoteTransactionStatus:
        ...
```

Клиент использует `self.session` (`ExternalApiSession`) для HTTP-запросов — это обеспечивает event log и метрики.

**Sandbox Client** — наследовать от основного клиента + `BaseSandboxClientMixin[T_Credentials]` из `payment/services/base_classes.py`.

Sandbox-клиент используется, когда `wallet.is_sandbox=True`. Он не делает реальных HTTP-запросов, а возвращает фиксированные ответы. `BaseSandboxClientMixin` автоматически планирует approve транзакции через `sandbox_finalization_delay_seconds`.

```python
class MySystemSandboxClient(
    base_classes.BaseSandboxClientMixin[MySystemCredentials], MySystemClient
):
    def deposit(self) -> entities.PaymentClientDepositResponse:
        return entities.PaymentClientDepositResponse(
            status=TransactionStatus.PENDING,
            raw_response={"id": "fake"},
            id_in_payment_system=sandbox_services.get_random_id(
                PaymentSystemType.MY_SYSTEM
            ),
        )

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        return entities.PaymentClientWithdrawResponse(
            status=TransactionStatus.PENDING,
            id_in_payment_system=sandbox_services.get_random_id(
                PaymentSystemType.MY_SYSTEM
            ),
            raw_response={"id": "fake"},
        )
```

**Entities (DTO)** — определяются в `entities.py` интеграции или используются общие из `payment/entities.py`.

Ключевые DTO для ответов клиента:

```python
# payment/entities.py — уже определены, не нужно создавать заново

class PaymentClientDepositResponse(BaseModel):
    status: Literal[TransactionStatus.PENDING, TransactionStatus.FAILED]
    raw_response: dict[str, Any]
    id_in_payment_system: str | None = None
    decline_code: str | None = None
    decline_reason: str | None = None
    customer_redirect_form_data: TransactionExtraFormData | None = None

class PaymentClientWithdrawResponse(BaseModel):
    # FAILED только если 100% уверены, что деньги НЕ отправлены
    status: Literal[TransactionStatus.PENDING, TransactionStatus.FAILED]
    id_in_payment_system: str | None
    raw_response: dict[str, Any] | list[Any]
    decline_code: str | None = None
    decline_reason: str | None = None
```

Credentials-модель определяется в `entities.py` интеграции:

```python
class MySystemCredentials(BaseModel):
    api_key: pydantic.SecretStr
    merchant_id: str
    base_url: str
```

**Controller** — наследовать `PaymentSystemController[T_Client, T_SandboxClient]` из `payment/systems/base_controller.py`:

```python
class MySystemController(
    PaymentSystemController[MySystemClient, MySystemSandboxClient]
):
    client_cls = MySystemClient
    sandbox_client_cls = MySystemSandboxClient

    def _run_deposit(self, trx_id: types.TransactionId, client: ...) -> None:
        ...

    def _run_withdraw(self, trx: PaymentTransaction, client: ...) -> None:
        ...

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        ...

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        ...

# Инстанцирование на уровне модуля
my_system_controller = MySystemController(
    payment_system=PaymentSystemType.MY_SYSTEM,
    default_credentials={...},
)
```

**Views** — наследовать `GenericPaymentSystemApiV1Mixin` из `payment/api_v1/views.py` + `viewsets.GenericViewSet`.

Миксин предоставляет готовые методы `_generic_deposit(...)` и `_generic_withdraw(...)`, которые обрабатывают создание транзакции через стандартные сериализаторы:

```python
@extend_schema(tags=["MySystem"])
class MySystemViewSet(
    GenericPaymentSystemApiV1Mixin,
    viewsets.GenericViewSet[Any],
):
    @extend_schema(
        operation_id="Create MySystem deposit transaction",
        request=DepositTransactionRequestSerializer,
    )
    @action(detail=False, methods=["post"])
    def deposit(self, request: Request) -> Response:
        return self._generic_deposit(
            request.data, serializer_class=DepositTransactionRequestSerializer
        )

    @extend_schema(
        operation_id="Create MySystem withdrawal transaction",
        request=WithdrawalTransactionRequestSerializer,
    )
    @action(detail=False, methods=["post"])
    def withdraw(self, request: Request) -> Response:
        return self._generic_withdraw(
            request.data, serializer_class=WithdrawalTransactionRequestSerializer
        )
```

Если интеграция использует кастомные поля в запросе — создать свой сериализатор, наследующий от `DepositTransactionRequestSerializer` / `WithdrawalTransactionRequestSerializer`.

#### Маппинг статусов

Каждая интеграция определяет маппинг статусов провайдера → `TransactionStatus`:

```python
_operation_status_by_foreign_status = {
    "pending": TransactionStatus.PENDING,
    "processing": TransactionStatus.PENDING,
    "complete": TransactionStatus.SUCCESS,
    "failed": TransactionStatus.FAILED,
}
```

#### Использование `PaymentTransaction.extra`

`extra` (JSONField) — хранилище provider-specific данных, которые не укладываются в стандартные поля транзакции. Типичные случаи:

- Промежуточные идентификаторы от провайдера, нужные для status check (пример: `fetchaOperation` в Paycash).
- Дополнительные данные из callback, необходимые для дальнейшей обработки.

```python
trx.extra["provider_session_id"] = response_data["session_id"]
trx.save_extra()
```

Правила:

- Не хранить в `extra` секреты и PII.
- Использовать `trx.save_extra()` вместо `trx.save()`, если меняется только `extra`.
- Ключи называть snake_case, без префикса имени провайдера (контекст уже задан типом системы).

#### Регистрация

1. Добавить значение в `PaymentSystemType` (`common/const.py`).
2. Зарегистрировать контроллер в `payment/controller_registry.py` → `PAYMENT_SYSTEMS`.
3. Добавить URL-роуты в `payment/api_v1/urls.py`.

### 5. Добавить тесты

Правила тестирования — в `.agents/skills/django-testing/SKILL.md`.

Обязательный минимум для интеграции:

- Happy path `deposit` (создание → запрос к провайдеру → callback → SUCCESS).
- Happy path `withdraw` (создание → запрос → callback → SUCCESS).
- Failure path: ошибка от провайдера → FAILED.
- Failure path: специфичные для интеграции (например, нет привязанного аккаунта).

Тесты в `tests/payment/systems/<system_name>/`.

### 6. Финализация

- Обновить дизайн-документ итоговыми примечаниями по реализации (секция "Контекст для будущих итераций").

## Жёсткие ограничения

- Никаких правок кода до утверждённого дизайн-документа.
- Не хранить секреты в коде/документации/тестах.
- Стандартные переходы статусов синхронизировать через `sync_remote_status_with_transaction(...)`.
  Исключения: `refund`/`chargeback`/`chargeback reversal` в контролируемых service-сценариях transaction-processing с обязательными balance side-effects и доменным аудитом.
- Для HTTP-запросов к провайдеру использовать `self.session` (ExternalApiSession), не `requests` напрямую.
- Не выполнять HTTP-вызовы к провайдеру внутри открытой DB-транзакции.
