---
name: python-class-rules
globs:
  - "rozert_pay/**/*.py"
description: "Использовать для задач, где добавляются или меняются Python/Django-классы в rozert-pay: admin-классы, service/base-классы, контроллеры, клиенты и DTO."
---

# Правила Написания Классов В rozert-pay

Используй этот навык, когда в задаче создаются или меняются классы.
Общие правила именования, логирования и fail-fast дополнительно брать из `.agents/skills/code-style/SKILL.md`.

## Когда НЕ использовать

- Если задача про Django-модели: использовать `.agents/skills/django-model-rules/SKILL.md`.
- Изменения только в функциях без новых/изменяемых классов.
- Чисто документарные правки.

## 1. Сначала выбрать правильный тип класса

- `Admin`/`Form` — только для представления и валидации в Django admin.
- `Service class` — когда нужна stateful-оркестрация из нескольких шагов.
- `Client`/`Controller` — для внешних платежных систем (интеграционный слой).
- `DTO` — по умолчанию `pydantic.BaseModel`; `TypedDict` только для very large batch-сценариев.

Если состояние не требуется, предпочитай функцию, а не класс.

## 2. Структура класса

Порядок внутри класса:

1. class attributes/конфигурация (`form_cls`, `client_cls`, `credentials_cls`).
2. `__init__` с минимальной инициализацией без тяжёлых side-effects.
3. публичные методы API.
4. protected hooks (`_run_*`, `_parse_*`, `_get_*`) для расширения.
5. технические helper-методы.

Примеры паттерна:

- `rozert_pay/payment/services/base_classes.py` (`BasePaymentClient`)
- `rozert_pay/payment/services/transaction_actualization.py` (`BaseTransactionActualizer`)
- `rozert_pay/payment/services/transaction_set_status.py` (`BaseTransactionSetter`)

## 3. Правила для base-классов и наследования

- Базовые классы именовать `Base*`.
- В base-классе держать стабильный публичный API и инварианты.
- Вариативную логику выносить в protected hooks, которые реализуют наследники.
- Для обязательных hooks использовать `raise NotImplementedError`.
- Для методов, которые нельзя переопределять, использовать `@final`.
- Если метод работает только с class-level конфигурацией, делать `@classmethod`.

## 4. Состояние и побочные эффекты

- В `__init__` только сохранить параметры и собрать лёгкие зависимости.
- DB/HTTP операции делать в явных методах, а не в конструкторе.
- Для ленивого доступа к данным использовать `@cached_property` (пример: `BasePaymentClient.trx`).
- Свойства `@property` оставлять только для дешёвых вычислений/доступа к уже загруженным данным.

## 5. Admin-классы

- Admin-класс остаётся тонким, без бизнес-логики.
- Конфигурацию держать в class attrs (`list_display`, `list_filter`, `readonly_fields` и т.д.).
- Общие части выносить в base/mixin-классы (пример: `CategoryLimitAdminBase`, `BaseLimitAdmin`).

Ориентиры:

- `rozert_pay/limits/admin/base.py`
- `rozert_pay/limits/admin/customer_limits.py`
- `rozert_pay/limits/admin/merchant_limits.py`

## 6. DTO и классы-контракты

- По умолчанию использовать `pydantic.BaseModel` для DTO и классов-контрактов.
- `TypedDict` использовать только в местах, где обрабатывается потенциально большой список (больше нескольких тысяч сущностей) и валидация `BaseModel` даст заметный perf-overhead.
- Для внешних callback payload можно разрешать лишние поля через `ConfigDict(extra="allow")`.

Ориентиры:

- `rozert_pay/limits/services/limits.py` (`TypedDict`)
- `rozert_pay/payment/systems/bitso_spei/bitso_spei_controller.py` (`BaseModel` payload)

## 7. Fail-fast и наблюдаемость внутри классов

- Проверять обязательные предпосылки рано (`assert`, guard clauses, доменные ошибки).
- Не глотать исключения; добавлять контекст и пробрасывать/маппить в `Error`.
- Для публичных service-методов использовать измерение длительности (`@track_duration`) где это уже проектный паттерн.
- Логировать структурированно через `logger` модуля, без утечки чувствительных данных.

## 8. Чего избегать

- Классы «на будущее» без фактического состояния/поведения.
- Тяжёлые действия в `__init__` (DB lock, внешний HTTP).
- Смешивание доменной логики с transport/UI-слоем (views/admin/serializers).
- Динамический dispatch через `getattr` в прикладном коде, когда можно сделать явные ветки.
- Использование `dataclass`/`dataclasses` в проектном коде.

## 9. Чеклист перед завершением

- Выбран правильный тип класса для задачи.
- Публичный API и hooks разделены.
- Инварианты и fail-fast проверки стоят рядом с точкой использования.
- Нет бизнес-логики в admin/views/serializers.
- Для новых/изменённых моделей применены правила из `.agents/skills/django-model-rules/SKILL.md`.
- Для тестов на изменённые классы применены правила из `.agents/skills/django-testing/SKILL.md`.
