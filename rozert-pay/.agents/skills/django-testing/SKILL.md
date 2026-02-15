---
name: django-testing
globs:
  - "tests/**/*.py"
  - "tests/**/conftest.py"
description: Использовать для написания, изменения или ревью тестов в rozert-pay. Содержит правила моков, фабрик, фикстур, маркеров и запуска проверок.
---

# Тестирование В rozert-pay

Используй этот навык при написании, изменении или ревью тестов. Это исчерпывающий справочник по тестированию в проекте.

## Когда НЕ использовать

- Изменения только в production-коде без затрагивания тестов.
- Запуск проверок без изменения самих тестов (правила запуска кратко в каждом скилле).

## Структура тестов

```
tests/
├── conftest.py                  # Общие фикстуры: user, merchant, api_client, requests_mocker
├── factories.py                 # Все фабрики (factory_boy)
├── helpers/                     # Утилиты: prometheus, matchers
├── payment/
│   ├── conftest.py              # Фикстуры кошельков, ExternalTestClient
│   ├── api_v1/                  # Тесты API v1
│   │   └── matchers.py          # DictContains и другие матчеры
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

Все фабрики в `tests/factories.py`. Использовать `DjangoModelFactory`, **не** `Model.objects.create(...)` напрямую.

```python
# GOOD — фабрика с SubFactory и Sequence для уникальности
class MerchantFactory(DjangoModelFactory[Merchant]):
    name = factory.Sequence(lambda n: f"Merchant {n}")
    merchant_group = factory.SubFactory(MerchantGroupFactory)
    secret_key = factory.Faker("uuid4")

    class Meta:
        model = Merchant


class PaymentTransactionFactory(DjangoModelFactory["db_services.LockedTransaction"]):
    wallet = factory.SubFactory(CurrencyWalletFactory)
    amount = 100
    type = TransactionType.DEPOSIT
    currency = "USD"
    callback_url = "http://callback"
    redirect_url = "http://redirect"

    class Meta:
        model = PaymentTransaction

# BAD — ручное создание, дублирование, хрупкость
trx = PaymentTransaction.objects.create(
    wallet=wallet, amount=100, type="deposit", currency="USD",
    callback_url="http://callback", redirect_url="http://redirect",
)
```

Правила:

- Новые фабрики добавлять в `tests/factories.py`.
- `factory.Sequence(...)` для полей с `unique=True` — предотвращает flaky-тесты.
- `factory.SubFactory(...)` для FK-зависимостей.
- Кастомный `_create` — только когда нужна пост-обработка (например, `set_password`).

### 2. Фикстуры

Общие фикстуры — в `tests/conftest.py`, доменные — в `tests/<domain>/conftest.py`.

```python
# tests/conftest.py — базовые
@pytest.fixture
def api_client() -> APIClient:
    return APIClient()

@pytest.fixture
def merchant(db):
    return MerchantFactory.create()

@pytest.fixture
def merchant_client(api_client, merchant) -> APIClient:
    force_authenticate(api_client, merchant)
    return api_client

# tests/payment/conftest.py — доменные
@pytest.fixture
def wallet_paycash(merchant: models.Merchant) -> models.Wallet:
    return WalletFactory.create(
        merchant=merchant,
        system__type=PaymentSystemType.PAYCASH,
        system__name="PayCash",
        default_callback_url="https://callbacks",
        credentials=dict(
            host="http://fake.com",
            emisor="fake",
            key="fake",
        ),
    )
```

Правила:

- Общие фикстуры (`user`, `merchant`, `api_client`) — в `tests/conftest.py`.
- Доменные фикстуры (кошельки, моки провайдеров) — в `tests/<domain>/conftest.py`.
- Не дублировать фикстуры между conftest-файлами.
- Фикстуры для wallet-ов создавать с реалистичными `credentials`.

### 3. Моки внешних HTTP-запросов

**Единственный** инструмент для HTTP-моков — `requests_mock`. Без `unittest.mock.patch` на `requests.post/get`.

```python
# GOOD — requests_mock через context manager из conftest
from tests.conftest import requests_mocker

def test_deposit_success(self, api_client, merchant, wallet_paycash):
    force_authenticate(api_client, merchant)

    with requests_mocker() as m:
        m.post(
            "http://fake.com/v1/reference",
            json={"Reference": "1522289200026"},
        )
        response = api_client.post(url, data=payload)
        assert response.status_code == 200


# GOOD — requests_mock напрямую для unit-теста
def test_write_error_request(self):
    with requests_mock.Mocker() as m:
        m.post("http://test", status_code=500, json={"error": "error"})

        trx = PaymentTransactionFactory.create()
        sess = external_api_services.get_external_api_session(
            trx_id=trx.id, timeout=10,
        )
        sess.post("http://test")

        assert PaymentTransactionEventLog.objects.count() == 1


# GOOD — requests_mock как fixture
@pytest.fixture
def mock_bitso_api_response() -> Generator[requests_mock.Mocker, None, None]:
    with requests_mock.Mocker() as m:
        m.get("https://bitso.com/api/v3/banks/MX", json={...})
        yield m


# BAD — unittest.mock на requests
@mock.patch("requests.post")
def test_deposit(self, mock_post):
    mock_post.return_value.json.return_value = {"status": "ok"}
```

Правила:

- Для end-to-end тестов API: `requests_mocker()` из `tests/conftest.py` (автоматически мокает callback-ы).
- Для unit-тестов: `requests_mock.Mocker()` напрямую.
- Повторяемые моки провайдеров — выносить в фикстуры (`tests/payment/conftest.py`).
- Мокать **только** внешние HTTP-запросы; внутреннюю логику не мокать.
- Моки минимальные — только те endpoints, которые вызываются в тесте.

### 4. Маркеры и структура тестов

```python
# Маркер на уровне модуля — все тесты в файле используют DB
pytestmark = pytest.mark.django_db


# Маркер на уровне класса
@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestCustomerLimits:
    @pytest.fixture
    def customer_limit(self, customer):
        return CustomerLimitFactory.create(customer=customer)

    def test_limit_exceeded(self, customer, customer_limit):
        ...


# Параметризация
@pytest.mark.parametrize(
    "payload, expected_error",
    [
        ({}, {"amount": [ErrorDetail(string="This field is required.", code="required")]}),
        ({"amount": -1}, {"amount": [ErrorDetail(string="...", code="...")]}),
    ],
)
def test_validation_errors(self, api_client, merchant, payload, expected_error):
    ...
```

Правила:

- `@pytest.mark.django_db` — обязателен для тестов с БД. Предпочитать `pytestmark` на уровне модуля.
- `@pytest.mark.usefixtures("disable_cache")` — для тестов, где кеш мешает.
- `@pytest.mark.parametrize` — для проверки нескольких вариантов входных данных.
- Тесты группировать в классы по функциональности.
- Имена тестов: `test_<что_тестируем>_<сценарий>` (например, `test_deposit_success`, `test_limit_exceeded`).

### 5. Что тестировать

- **Happy path** — основной сценарий работает.
- **Failure path** — ошибки обрабатываются корректно (невалидные данные, таймауты, ошибки провайдера).
- **Для платежных интеграций**: обязательны happy path тесты для `deposit` и `withdraw`.
- **Для изменений статусов**: проверять переходы и балансовые side-effects.
- **Для исключений по статусам** (`refund`/`chargeback`/`chargeback reversal`): отдельно проверять разрешенный прямой status-update в service-коде, корректные balance side-effects и наличие доменного аудита.
- **Edge cases**: конкурентный доступ, пустые данные, граничные значения лимитов.

### 6. Вспомогательные утилиты

- `tests/payment/api_v1/matchers.py` — `DictContains` для частичного сравнения dict-ов.
- `tests/helpers/prometheus.py` — `has_metric_line(...)` для проверки метрик.
- `tests/payment/conftest.py` — `ExternalTestClient` для интеграционных тестов через клиент.
- `tests/conftest.py` — `track_error_logs` (autouse) — автоматически ловит неожиданные `logger.error` и фейлит тест.

### 7. Запуск проверок

```bash
# Таргетные тесты (всегда — минимум)
DJANGO_SETTINGS_MODULE=rozert_pay.settings_unittest pytest tests/payment/services/test_transaction_processing.py

# Или через make
make pytest -- tests/payment/services/test_transaction_processing.py

# Типизация (всегда при изменении Python-кода)
make mypy

# Линтинг (при широких стилевых изменениях)
make lint
make pylint

# Полный набор (при критичных платежных изменениях)
make mypy && make lint && make pylint && make pytest
```

Уровни проверок:

- **Минимум**: таргетные тесты + `make mypy`.
- **Стилевые**: + `make lint` + `make pylint`.
- **Критичные платежные**: полный набор `make mypy`, `make lint`, `make pylint`, `make pytest`.

## Жёсткие ограничения

- HTTP-моки — **только** `requests_mock`. Без `unittest.mock.patch` на `requests.*`.
- Мокать **только** внешние HTTP-запросы; не мокать внутреннюю логику.
- Не хранить секреты в тестах (реальные API-ключи, токены).
- Не дублировать фабрики и фикстуры — переиспользовать существующие.
- Не создавать объекты через `Model.objects.create(...)` если есть фабрика.
