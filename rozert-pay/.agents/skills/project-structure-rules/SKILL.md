---
name: project-structure-rules
globs:
  - "rozert_pay/**/*.py"
  - "tests/**/*.py"
description: Использовать для задач, где создаются новые Django app/модули или меняется структура проекта в rozert-pay (раскладка по app, modules, services, const, api, tasks, payment systems).
---

# Структура Проекта И Модулей В rozert-pay

Используй этот навык, когда задача затрагивает создание/реорганизацию app и модулей.
Для стилевых правил кода дополнительно использовать `.agents/skills/code-style/SKILL.md`.

## Когда НЕ использовать

- Чисто локальные изменения логики внутри существующего модуля без структурных изменений.
- Изменения только в тестах без изменения структуры production-кода.

## 1. Базовая структура app

Каждый app размещается в `rozert_pay/<app_name>/`.
Минимальный базовый набор:

- `__init__.py`
- `migrations/`
- `models.py` или пакет `models/`
- `admin.py` или пакет `admin/`

Опциональные части подключаются по потребности:

- `services/` для доменной логики
- `tasks.py` или пакет `tasks/` для Celery
- `const.py` для локальных констант app
- `templates/` только если есть server-side template/admin templates
- `management/commands/` только если нужны management commands

## 2. Регистрация app и инициализация

- Новый app должен быть добавлен в `INSTALLED_APPS` (`rozert_pay/settings.py`).

Ориентиры:

- `rozert_pay/payment/apps.py`
- `rozert_pay/balances/apps.py`
- `rozert_pay/settings.py`

## 3. `const`, `services`, `helpers`: что где хранить

`const.py`:

- Константы и декларации значений: `TextChoices`/`StrEnum`, string keys, regex, channel names, feature flags, default values.
- Допустимы простые env-based выборы на импорт (`if settings.IS_PRODUCTION: ...`) без side-effects.
- Нельзя размещать бизнес-логику, ORM, HTTP, мутации состояния.

`services/`:

- Прикладная/доменная логика и orchestration use-case.
- Допускаются ORM-запросы, транзакции, блокировки, внешние API-вызовы, доменный аудит/логирование.
- Сервис — точка принятия бизнес-решений.

`common/helpers/`:

- Инфраструктурные утилиты, переиспользуемые между app.
- Helpers должны быть максимально доменно-нейтральными (formatting/parsing, cache wrappers, thread-local/context utils, small adapters).
- Ключевые бизнес-правила в helpers не выносить.

Ориентиры:

- `const`: `rozert_pay/common/const.py`, `rozert_pay/limits/const.py`
- `services`: `rozert_pay/payment/services/`, `rozert_pay/limits/services/`
- `helpers`: `rozert_pay/common/helpers/`

## 4. Когда делать `models.py` vs `models/`

- Если моделей мало и они связаны одной областью, использовать `models.py`.
- Если моделей много или есть явные поддомены, использовать пакет `models/` с разбиением по файлам.
- При использовании `models/` экспортировать публичные модели из `models/__init__.py` для стабильных импортов.

Ориентиры:

- `models.py`: `rozert_pay/payment/models.py`, `rozert_pay/balances/models.py`
- `models/`: `rozert_pay/limits/models/`, `rozert_pay/payment_audit/models/`

## 5. Когда делать `admin.py` vs `admin/`

- Если админка простая — `admin.py`.
- Если админка большая/по нескольким сущностям — пакет `admin/` с разбиением по ресурсам и сборкой через `admin/__init__.py`.
- Админка остаётся тонким слоем; бизнес-решения остаются в `services`.

Ориентиры:

- `admin.py`: `rozert_pay/balances/admin.py`
- `admin/`: `rozert_pay/payment/admin/`, `rozert_pay/limits/admin/`

## 6. API-структура

- Публичный API выносить в `api_v1/`, backoffice API — в `api_backoffice/`.
- Внутри API-модуля держать как минимум `urls.py`; views/serializers группировать по домену.
- Подключение маршрутов app делать в корневом `rozert_pay/urls.py`.

Ориентиры:

- `rozert_pay/payment/api_v1/`
- `rozert_pay/payment/api_backoffice/`
- `rozert_pay/account/urls.py`
- `rozert_pay/urls.py`

## 7. Celery-задачи

- App-level задачи размещать в `tasks.py` app или тематическом `tasks/` пакете.
- Для очередей использовать `CeleryQueue` из `common.const`, не строковые литералы.
- Передавать в задачи только идентификаторы сущностей, не ORM-объекты.

Ориентиры:

- `rozert_pay/payment/tasks.py`
- `rozert_pay/common/tasks.py`
- `rozert_pay/payment/systems/*/tasks.py`

## 8. Паттерн для payment systems

Новые интеграции размещаются в `rozert_pay/payment/systems/<provider>/`.
Минимально ожидаемые модули: `controller.py` и `client.py` (или эквивалент существующего стиля в app).
Дополнительно по необходимости: `const.py`, `models.py`, `tasks.py`, `views.py`, `audit.py`.

Обязательно:

- зарегистрировать контроллер в `payment/controller_registry.py`;
- использовать фабрики доступа через `payment/factories.py`;
- не обходить базовый контракт `PaymentSystemController`.

## 9. Чеклист структурных изменений

- Для нового app: добавлен в `INSTALLED_APPS`, есть `migrations/`, корректная регистрация URL/admin/tasks.
- Новые модули лежат в правильном слое (`const` vs `services` vs `helpers`).
- При укрупнении области выполнено разбиение `models.py/admin.py` в пакетную структуру.
- Нет циклических импортов из-за неправильного размещения кода.
- Новые структурные правила и связи отражены в релевантных skills/документации.
