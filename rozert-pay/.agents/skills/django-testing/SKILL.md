---
name: django-testing
globs:
  - "tests/**/*.py"
description: Использовать для написания, изменения или ревью тестов в rozert-pay. Содержит правила моков, фабрик, фикстур, маркеров и запуска проверок.
---

# Тестирование в rozert-pay

## Когда НЕ использовать

- Изменения только в production-коде без затрагивания тестов.
- Запуск проверок без изменения самих тестов.

## Структура тестов

```
tests/
├── conftest.py                  # Общие фикстуры: user, merchant, api_client, requests_mocker
├── factories.py                 # Все фабрики (factory_boy)
├── helpers/                     # Утилиты: prometheus, matchers
├── payment/
│   ├── conftest.py              # Фикстуры кошельков, ExternalTestClient
│   ├── api_v1/                  # Тесты API v1 + matchers.py (DictContains)
│   ├── api_backoffice/          # Тесты backoffice API
│   ├── services/                # Тесты сервисного слоя
│   └── systems/                 # Тесты интеграций с платежными системами
├── balances/                    # Тесты балансов
├── limits/                      # Тесты лимитов
├── risk_lists/                  # Тесты risk-lists
└── account/                     # Тесты аккаунтов
```

## Порядок работы

### 1. Фабрики (factory_boy)

Все фабрики в `tests/factories.py`. Использовать `DjangoModelFactory`, **не** `Model.objects.create(...)`.

```python
class MerchantFactory(DjangoModelFactory[Merchant]):
    name = factory.Sequence(lambda n: f"Merchant {n}")       # unique-поля
    merchant_group = factory.SubFactory(MerchantGroupFactory) # FK
    secret_key = factory.Faker("uuid4")
    class Meta:
        model = Merchant

class CurrencyWalletFactory(DjangoModelFactory[CurrencyWallet]):
    operational_balance = 1000
    pending_balance = 0
    balance = factory.LazyAttribute(lambda o: o.operational_balance - o.pending_balance)
    class Meta:
        model = CurrencyWallet
```

Правила:

- Новые фабрики — в `tests/factories.py`.
- `factory.Sequence(...)` для `unique=True`-полей.
- `factory.SubFactory(...)` для FK.
- `factory.LazyAttribute(...)` / `@factory.lazy_attribute` для вычисляемых полей.
- Кастомный `_create` — только для пост-обработки (например, `set_password`).

### 2. Фикстуры

Общие — в `tests/conftest.py`, доменные — в `tests/<domain>/conftest.py`. Перед созданием новой — проверить каталог:

| Фикстура | Что делает |
|---|---|
| `user` | `User` через `UserFactory` с паролем `"123"` |
| `api_client` | Пустой `APIClient` без авторизации |
| `merchant` / `merchant_client` | `Merchant` + авторизованный `APIClient` |
| `customer` | `Customer` через `CustomerFactory` |
| `merchant_sandbox` / `merchant_sandbox_client` | Sandbox-мерчант + клиент |
| `wallet` / `wallet_spei` / `wallet_paypal` / `wallet_conekta_oxxo` | Кошельки с credentials |
| `disable_cache` | Отключает кэш |
| `track_error_logs` **(autouse)** | Ловит `logger.error` → фейлит тест |
| `disable_error_logs` | Отключает `track_error_logs` для тестов failure path |
| `mock_on_commit` | `on_commit` синхронно (подробности → секция 3b) |
| `disable_celery_task` | Мокает `celery.Task.apply_async` (подробности → секция 3b) |
| `mock_send_callback` / `mock_check_status_task` | Мокают Celery-задачи |
| `mock_slack_send_message` | Мокает Slack |

Правила:

- Не дублировать фикстуры между conftest-файлами.
- Wallet-фикстуры — с реалистичными `credentials`.
- Только `scope="function"` для фикстур с БД. `scope="session"` / `scope="module"` сломает изоляцию.
- **`track_error_logs`**: если тест **намеренно** вызывает `logger.error` (failure path), добавить `disable_error_logs`:

```python
def test_provider_timeout(self, disable_error_logs, wallet_spei):
    with requests_mocker() as m:
        m.post("http://spei/v1/pay", exc=requests.exceptions.Timeout)
        response = api_client.post(url, data=payload)
    assert response.status_code == 408
```

### 3. Моки

#### 3a. HTTP — только `requests_mock`

Запрещено: `unittest.mock.patch` на `requests.post/get/…`.

```python
from tests.conftest import requests_mocker

# E2E: requests_mocker() автоматически мокает callback-ы
def test_deposit_success(self, api_client, merchant, wallet_paycash):
    force_authenticate(api_client, merchant)
    with requests_mocker() as m:
        m.post("http://fake.com/v1/reference", json={"Reference": "123"})
        response = api_client.post(url, data=payload)
        assert response.status_code == 200

# Unit: requests_mock.Mocker() напрямую
def test_write_error_request(self):
    with requests_mock.Mocker() as m:
        m.post("http://test", status_code=500, json={"error": "error"})
        ...
```

- E2E: `requests_mocker()` из conftest (мокает callback-ы автоматически).
- Unit: `requests_mock.Mocker()` напрямую.
- Повторяемые моки → выносить в фикстуры. Мокать минимально — только вызываемые endpoints.

#### 3b. Celery и `on_commit`

`unittest.mock.patch` допустим для side-effect-ов. Использовать готовые фикстуры из conftest.

```python
# mock_on_commit: on_commit синхронно
def test_callback_sent(self, mock_on_commit, mock_send_callback):
    process_transaction(trx.id)
    mock_send_callback.assert_called_once()

# django_capture_on_commit_callbacks: точный контроль
# ВАЖНО: требует transaction=True
@pytest.mark.django_db(transaction=True)
def test_task_scheduled_on_commit(self, wallet_spei):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        api_client.post(url, data=payload)
    assert len(callbacks) == 1

# Синхронный запуск Celery-задачи в тесте
process_transaction.apply(kwargs={"transaction_id": trx.id})
```

- `disable_celery_task` — задачи не уходят в очередь.
- `mock_on_commit` — `on_commit` синхронно.
- `django_capture_on_commit_callbacks` (import: `from django.test.utils import CaptureOnCommitCallbacks`) — **требует** `@pytest.mark.django_db(transaction=True)`, иначе `on_commit` не срабатывает.
- `task.apply(kwargs={...})` — синхронный запуск задачи.
- Не создавать свои моки Celery/on_commit — переиспользовать фикстуры.

### 4. Маркеры и структура

```python
pytestmark = pytest.mark.django_db  # на уровне модуля — предпочтительно

@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestCustomerLimits:
    def test_limit_exceeded(self, customer, customer_limit): ...
```

- `django_db` — обязателен для тестов с БД.
- `django_db(transaction=True)` — для тестов с `on_commit` / `django_capture_on_commit_callbacks`.
- `usefixtures("disable_cache")` — где кеш мешает.
- `parametrize` — для нескольких вариантов входных данных.
- Тесты группировать в классы. Имена: `test_<что>_<сценарий>`.

### 5. Что тестировать

- **Happy path** — основной сценарий.
- **Failure path** — невалидные данные, таймауты, ошибки провайдера.
- **Платежные интеграции**: обязательны happy path для `deposit` и `withdraw`.
- **Статусы**: переходы + балансовые side-effects.
- **Исключения** (`refund`/`chargeback`/`chargeback reversal`): прямой status-update, balance side-effects, доменный аудит.
- **Edge cases**: конкурентный доступ, пустые данные, граничные значения.

**`refresh_from_db()` после мутаций** — Python-объект не обновляется при изменении в БД:

```python
trx = PaymentTransactionFactory.create(status=TransactionStatus.PENDING)
process_transaction(trx.id)
trx.refresh_from_db()  # обязательно перед assert
assert trx.status == TransactionStatus.SUCCESS
```

## Инструменты

### `pytest.raises`

```python
with pytest.raises(ValidationError, match=".*already exists.*"):
    create_customer_limit(customer=customer, ...)

with pytest.raises(ValueError) as exc_info:
    calculate_clabe_check_digit("123")
assert "18 digits" in str(exc_info.value)
```

- Всегда `pytest.raises`, не `try/except`.
- `match=` для проверки текста. Для `ValidationError` — проверять поля и коды.

### `freezegun`

```python
from freezegun import freeze_time

@freeze_time("2023-01-01")  # декоратор — один момент
def test_validate_expiration(self): ...

# context manager — несколько моментов в одном тесте
now = timezone.now()
with freeze_time(now - timedelta(minutes=16)):
    trx = PaymentTransactionFactory.create(status=TransactionStatus.PENDING)
with freeze_time(now):
    tasks.task_fail_by_timeout(trx.id)
    trx.refresh_from_db()
    assert trx.status == TransactionStatus.FAILED
```

- Использовать `timezone.now()`, не `datetime.now()`.

### `override_settings`

```python
from django.test import override_settings

@override_settings(BACK_SECRET_KEY="test-secret")
def test_wrong_secret_key(self, api_client, db):
    response = api_client.post(url, HTTP_X_SECRET="wrong")
    assert response.status_code == 403
```

- Не менять `settings` напрямую — утечка в другие тесты.
- Для кэша предпочитать фикстуру `disable_cache`.

### Утилиты

- `tests/payment/api_v1/matchers.py` — `DictContains` для частичного сравнения dict-ов.
- `tests/helpers/prometheus.py` — `has_metric_line(...)` для метрик.
- `tests/payment/conftest.py` — `ExternalTestClient` для интеграционных тестов.

## Запуск проверок

```bash
make pytest -- tests/path/to/test_file.py   # таргетные тесты
make mypy                                    # типизация
make lint && make pylint                     # линтинг
make mypy && make lint && make pylint && make pytest  # полный набор
```

- **Минимум**: таргетные тесты + `make mypy`.
- **Стилевые**: + `make lint` + `make pylint`.
- **Критичные платежные**: полный набор.

## Жёсткие ограничения

- HTTP-моки — **только** `requests_mock`. Запрещено `unittest.mock.patch` на `requests.*`.
- `unittest.mock.patch` допустим для side-effect-ов, но предпочитать фикстуры из conftest.
- Не хранить секреты в тестах.
- Не дублировать фабрики и фикстуры — переиспользовать.
- Не `Model.objects.create(...)` если есть фабрика.
- Исключения — через `pytest.raises`, не `try/except`.
- Настройки — через `override_settings`, не `settings.X = ...`.
- Фикстуры с БД — только `scope="function"`.
