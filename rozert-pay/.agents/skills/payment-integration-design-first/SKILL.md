---
name: payment-integration-design-first
globs:
  - "rozert_pay/payment/systems/**/*.py"
  - "docs/integrations/**/*.md"
description: Использовать для новых и изменяемых платежных интеграций. Перед правками кода обязателен подтверждённый дизайн-документ. Покрывает полный цикл — от дизайна до регистрации контроллера.
---

# Проектирование Перед Разработкой Для Платежных Интеграций

Используй этот навык для задач по платежным интеграциям: новый провайдер, изменения флоу, изменения callback/статусов, добавление нового метода (deposit/withdraw).

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
- Валидация подписи
- Как искать транзакцию по callback-данным

## Структура интеграции
- Список файлов и их назначение
- Роуты (URL endpoints)
- Путь к тестам

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
- Статусы синхронизировать только через `sync_remote_status_with_transaction(...)`.
- Для HTTP-запросов к провайдеру использовать `self.session` (ExternalApiSession), не `requests` напрямую.
- Не выполнять HTTP-вызовы к провайдеру внутри открытой DB-транзакции.
