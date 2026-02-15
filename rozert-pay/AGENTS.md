# AGENTS.md — rozert-pay

Этот файл задает базовые правила работы AI-агентов внутри `rozert-pay/`.
Область действия: весь каталог `rozert-pay/` и подпапки.

## 1. Быстрый контекст

- Стек: Django + Celery + Postgres + Redis + RabbitMQ.
- Основной код: `rozert_pay/`.
- Тесты: `tests/`.
- Основные проверки: `make pytest`, `make mypy`, `make lint`, `make pylint`.

## 2. Команды запуска для агента

### Codex Web (cloud)

```bash
bash scripts/codex_setup.sh
bash scripts/codex_maintenance.sh
```

Если рабочая директория внутри `rozert-pay/`:

```bash
bash ../scripts/codex_setup.sh
bash ../scripts/codex_maintenance.sh
```

### Codex IDE / CLI (локально)

```bash
make pytest
make mypy
make lint
make pylint
```

## 3. Обязательные env-окружения (вне Docker)

- `PYTHONPATH=../shared-apps:$(pwd):${PYTHONPATH}`
- `DJANGO_SETTINGS_MODULE=rozert_pay.settings_unittest`
- `POSTGRES_HOST`, `POSTGRES_PORT`, `REDIS_HOST` (локальные значения)

## 4. Границы изменений

Можно менять:

- `rozert_pay/**`
- `tests/**`
- `code_checks/**`
- документацию внутри `rozert-pay/**`

Только при явной задаче:

- `Dockerfile`
- `docker-compose*.yml`

Не менять без отдельного запроса:

- `.helm/secrets.*`
- `volume_data/**`
- `front/**`
- `swagger.yml`, `swagger.json`

## 5. Архитектурные инварианты (коротко)

- Бизнес-логика живет в `services`-слое; модели/views/serializers/admin остаются тонкими.
- Для платежных статусов единая точка синхронизации: `PaymentSystemController.sync_remote_status_with_transaction(...)`.
- Не обновлять `PaymentTransaction.status` напрямую вне регламентированного transaction-processing флоу.
- Для операций, меняющих финансовые сущности, использовать `transaction.atomic()` и `select_for_update()`.
- Внешние HTTP-вызовы не выполнять внутри открытой DB-транзакции.
- Celery-задачам передавать только идентификаторы и запускать их через `transaction.on_commit(...)`/`execute_on_commit(...)`.
- Логирование делать структурированно (`extra={...}`), без утечки чувствительных данных, с `request_id` для сквозной трассировки.
- Использовать fail-fast: не скрывать исключения и не продолжать критичный флоу в некорректном состоянии.

## 6. Базовые стилевые правила

- Явный доступ к атрибутам (`obj.field`), без `getattr`/`setattr`/`hasattr`/`delattr` в прикладном коде.
- Имена в коде на английском, без транслитерации и неочевидных сокращений.
- Новые доменные модели: `BaseDjangoModel` по умолчанию, публичный идентификатор отдельным `uuid`-полем.
- Для денежных значений использовать `MoneyField`.
- Для PII использовать существующие паттерны шифрования/хеширования.

## 7. Стандарт выполнения задачи

1. Прочитать релевантный код в `rozert-pay/` и зависимости в `../shared-apps/`.
2. Внести минимально достаточные изменения.
3. Запустить минимум:
   - таргетные тесты по измененной функциональности;
   - `make mypy` при изменениях типизированного Python-кода.
4. Если затронута критичная платежная логика/статусы: `make mypy`, `make lint`, `make pylint`, `make pytest`.
5. В отчете указывать:
   - измененные файлы;
   - выполненные команды проверки;
   - что не запустилось (если есть).

## 8. Тестирование и импорты (база)

- Для HTTP-моков в тестах использовать `requests_mock`.
- Моки использовать по минимуму; по возможности мокать только внешние HTTP-запросы.
- Повторяемые моки выносить в фикстуры или context manager.
- Импорты: относительные только внутри текущего модуля (`.`), для соседних/верхних модулей использовать абсолютные.

## 9. Approval-first режим

- Не править код без явного разрешения разработчика.
- Сначала предложить план работ и получить подтверждение, затем вносить изменения.

## 10. Правило для задач по интеграции платежки

- Первый шаг всегда: создать/обновить дизайн-документ в `docs/integrations/**` и получить подтверждение.
- До утверждения дизайн-документа код не менять.
- Не хранить секреты в коде.
- Для новой/измененной интеграции обязательны happy path тесты для `deposit` и `withdraw`; моки только внешнего HTTP через `requests_mock`.
- При задачах по платежной интеграции также обновлять связанный контекстный документ.
- Если задача требует изменения в проекте `../back`, применять те же правила design-first и тестирования.

## 11. Работа с БД/Redis

- PostgreSQL: использовать read-only пользователя `codex_readonly` (см. `../scripts/create_codex_postgres_user.sh`).
- Без явного запроса не выполнять destructive SQL (`DROP`, `TRUNCATE`, массовые `UPDATE/DELETE`).
- Redis: по умолчанию только чтение.

## 12. Политика коммитов и критерии готовности

- Если делается commit, в сообщении указывать, что commit сделан AI-агентом.
  Пример: `[AI] Fix payout status transition for timeout callback`
- Готово, когда:
  - нет новых ошибок интерпретации/сборки;
  - релевантные проверки пройдены;
  - нет незапрошенных изменений в сторонних подсистемах;
  - при изменении моделей обновлена Django admin-конфигурация.

## 13. Детали вынесены в docs и skills

- Детальная архитектура платежного флоу: `docs/agents/payment-transaction-architecture.md`
- Детальные правила разработки и стиля: `docs/agents/engineering-style-guide.md`
- Операционный чеклист агента: `docs/agents/agent-runbook.md`
- Design-first playbook для интеграций платёжных систем: `docs/agents/payment-integration-playbook.md`
- Skill по платежному флоу: `skills/payment-transaction-workflow/SKILL.md`
- Skill по стилю кода и ограничениям: `skills/django-payment-code-style/SKILL.md`
- Skill по проектированию-перед-разработкой для интеграций: `skills/payment-integration-design-first/SKILL.md`
