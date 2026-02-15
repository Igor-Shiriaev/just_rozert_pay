# Архитектура PaymentTransaction (Для Агента)

## Ключевая сущность

- `PaymentTransaction` — центральная сущность deposit/withdrawal-флоу и источник истины по статусу операции.

## Пути создания

- Через API:
  - `DepositTransactionRequestSerializer.create`
  - `WithdrawalTransactionRequestSerializer.create`
- Через callback-флоу:
  - `transactions_created_on_callback.process_transaction_creation_on_callback`
- Канонический сервис создания:
  - `db_services.create_transaction(...)`

## Флоу обработки

- Транзакции, созданные через API, обрабатываются асинхронно через:
  - `controller.on_db_transaction_created_via_api`
  - `tasks.process_transaction`
- Начальный статус: `pending`.
- Перед вызовом провайдера выполняются pre-checks:
  - risk-lists (`risk_lists.services.checker`)
  - limits (`limits.services.limits`)
- При провале pre-checks транзакция должна завершаться контролируемым переходом в `failed` через контроллерный флоу.

## Правило синхронизации статуса

- Единственная точка синхронизации:
  - `PaymentSystemController.sync_remote_status_with_transaction(...)`
- Не изменять `trx.status` напрямую в произвольном бизнес-коде.
- Перед синхронизацией валидировать статус провайдера:
  - `transaction_status_validation.validate_remote_transaction_status(...)`
- `bypass_validation` допустим только в контролируемых service/admin-сценариях.

## Балансовые side-effects

Side-effects связаны с переходом статуса внутри синхронизации:

- `deposit + success` -> `OPERATION_CONFIRMED`
- `withdrawal + success` -> `SETTLEMENT_CONFIRMED`
- `withdrawal + failed` -> `SETTLEMENT_CANCEL`
- chargeback/refund/reversal -> специализированные обработчики в `transaction_processing`

Для withdrawals резервирование начинается при создании (`SETTLEMENT_REQUEST` в create-пути withdrawal serializer).

## Проверки pending и таймаут

- Pending-статус обрабатывается через:
  - `check_status_until`
  - `tasks.check_status`
  - `TransactionPeriodicCheckService`
- При истечении TTL депозит может быть принудительно завершен как `failed` по правилам флоу.

## Наблюдаемость

- Для платежного аудита использовать:
  - `event_logs.create_transaction_log(...)`
  - `PaymentTransactionEventLog`
- Не заменять доменный аудит только обычными logger-вызовами.

## Конкурентность и транзакции

- Для операций, меняющих платежные сущности, использовать `transaction.atomic()` + `select_for_update()`.
- Не выполнять внешние HTTP-вызовы внутри активной DB-транзакции.
- Запускать Celery через `transaction.on_commit(...)` или `execute_on_commit(...)`.
- Передавать в Celery-задачи идентификаторы (`trx_id`, `callback_id`), затем перечитывать ORM-объекты в самой задаче.
