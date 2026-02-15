---
name: payment-transaction-workflow
globs:
  - "rozert_pay/payment/services/transaction_processing.py"
  - "rozert_pay/payment/services/transaction_status_validation.py"
  - "rozert_pay/payment/services/db_services.py"
  - "rozert_pay/payment/systems/base_controller.py"
  - "rozert_pay/payment/tasks.py"
  - "rozert_pay/balances/**/*.py"
description: Использовать для задач, где меняются жизненный цикл PaymentTransaction, переходы статусов, callback-обработка, периодические проверки или балансовые side-effects в rozert-pay.
---

# Порядок Работы С PaymentTransaction

Используй этот навык, когда задача меняет поведение платежных статусов, обработку callback, флоу процессинга транзакции или балансовые операции.

## Когда НЕ использовать

- Изменения только в UI/admin без затрагивания статусной логики.
- Добавление полей в модель без влияния на флоу (→ `.agents/skills/django-model-rules/SKILL.md`).
- Новая интеграция с нуля (→ `.agents/skills/payment-integration-design-first/SKILL.md`).

## Ключевая сущность

`PaymentTransaction` — центральная сущность deposit/withdrawal-флоу и единственный источник истины по статусу операции.

## Переходы статусов

```
                    ┌───────────────────────────┐
                    │         PENDING           │
                    └──────┬──────────┬─────────┘
                           │          │
                      success      failed
                           │          │
                    ┌──────▼──┐  ┌────▼────┐
                    │ SUCCESS │  │ FAILED  │
                    └──┬───┬──┘  └─────────┘
                       │   │
              chargeback   refund
                       │   │
            ┌──────────▼─┐ ┌▼─────────┐
            │CHARGED_BACK│ │ REFUNDED │
            └──────┬─────┘ └──────────┘
                   │
                reversal
                   │
       ┌───────────▼──────────┐
       │CHARGED_BACK_REVERSAL │
       └──────────────────────┘
```

Статусы определены в `common/const.py` → `TransactionStatus`.

**Стандартная точка синхронизации:** `PaymentSystemController.sync_remote_status_with_transaction(...)` в `payment/systems/base_controller.py`.

**Явные исключения:** `refund`, `chargeback`, `chargeback reversal` в контролируемых service-сценариях transaction-processing, где прямое изменение `PaymentTransaction.status` допустимо только вместе с обязательными balance side-effects и доменным аудитом.

## Порядок работы

### 1. Определить scope изменений

Ключевые модули и что в них лежит:

| Модуль | Ответственность |
|---|---|
| `payment/systems/base_controller.py` | `sync_remote_status_with_transaction`, balance dispatch, callback parsing |
| `payment/services/transaction_processing.py` | `handle_chargeback`, `revert_to_pending`, `TransactionPeriodicCheckService` |
| `payment/services/transaction_status_validation.py` | `validate_remote_transaction_status` — валидация перед синхронизацией |
| `payment/services/db_services.py` | `get_transaction(for_update=...)`, `create_transaction(...)` |
| `payment/services/event_logs.py` | `create_transaction_log(...)` — доменный аудит |
| `payment/tasks.py` | `process_transaction`, `check_status`, `handle_incoming_callback` |
| `balances/services.py` | `BalanceUpdateService.update_balance(...)` |
| `payment/api_v1/serializers/` | Создание транзакций, `SETTLEMENT_REQUEST` при withdrawal |

### 2. Проверить флоу создания

Пути создания транзакции:

```python
# Через API (deposit/withdrawal)
DepositTransactionRequestSerializer.create(...)
WithdrawalTransactionRequestSerializer.create(...)

# Через callback (transaction-on-callback)
transactions_created_on_callback.process_transaction_creation_on_callback(...)

# Канонический сервис
db_services.create_transaction(...)
```

После создания через API:
1. `controller.on_db_transaction_created_via_api` → `tasks.process_transaction`
2. Начальный статус: `PENDING`
3. Pre-checks: risk-lists (`risk_lists.services.checker`) → limits (`limits.services.limits`)
4. При провале pre-checks → контролируемый переход в `FAILED`
5. Далее: `controller.run_deposit(trx_id)` или `controller.run_withdraw(trx_id)`

### 3. Проверить переходы статусов

Стандартные переходы выполняются через `sync_remote_status_with_transaction`. Перед синхронизацией обязательна валидация:

```python
# GOOD — через контроллер
clean_status = validate_remote_transaction_status(trx, remote_status)
controller.sync_remote_status_with_transaction(
    remote_status=clean_status,
    trx=locked_trx,
)

# BAD — прямое обновление
trx.status = TransactionStatus.SUCCESS
trx.save()  # нарушает инварианты, пропускает balance side-effects
```

`bypass_validation` допустим **только** в контролируемых service/admin-сценариях.
Для `refund`/`chargeback`/`chargeback reversal` допускается прямой статусный апдейт в service-коде transaction-processing при соблюдении балансовых и audit-инвариантов.

### 4. Проверить балансовые side-effects

Каждый переход статуса запускает балансовую операцию через `BalanceUpdateService.update_balance(...)`:

| Тип | Переход | BalanceEventType | Что происходит |
|---|---|---|---|
| deposit | → SUCCESS | `OPERATION_CONFIRMED` | +operational, +pending |
| withdrawal | создание | `SETTLEMENT_REQUEST` | +frozen (резервирование) |
| withdrawal | → SUCCESS | `SETTLEMENT_CONFIRMED` | -operational, -frozen |
| withdrawal | → FAILED | `SETTLEMENT_CANCEL` | -frozen (возврат резерва) |
| deposit | → CHARGED_BACK | `CHARGE_BACK` | -operational |

`SETTLEMENT_REQUEST` вызывается при создании withdrawal (в serializer), остальные — внутри `sync_remote_status_with_transaction`.

Пример chargeback:

```python
# payment/services/transaction_processing.py → handle_chargeback()
assert trx.status == TransactionStatus.SUCCESS
assert trx.type == TransactionType.DEPOSIT

trx.status = TransactionStatus.CHARGED_BACK
trx.extra[TransactionExtraFields.IS_CHARGEBACK_RECEIVED] = True
trx.save()

BalanceUpdateService.update_balance(
    BalanceUpdateDTO(
        currency_wallet=wallet,
        event_type=BalanceTransactionType.CHARGE_BACK,
        amount=Money(trx.amount.copy_abs(), trx.currency),
        payment_transaction=trx,
        initiator=InitiatorType.SYSTEM,
    )
)
```

### 5. Проверить callback-флоу

Цепочка обработки callback:

```
CallbackView.post()                          # payment/api_v1/views.py
  → IncomingCallback.objects.create(...)      # сохраняем сырой callback
  → handle_incoming_callback(cb_id)           # payment/tasks.py
    → controller.parse_callback(cb)           # base_controller.py — парсинг + валидация
      → _parse_callback(cb)                   # конкретная интеграция
      → validate_remote_transaction_status()  # валидация
      → sync_remote_status_with_transaction() # синхронизация статуса + баланс
```

### 6. Проверить периодические проверки статуса

`TransactionPeriodicCheckService` (в `transaction_processing.py`) управляет расписанием:

- Первые 5 проверок — каждую минуту.
- Следующие 6 — каждые 5 минут.
- Следующие 4 — каждые 15 минут.
- Далее — каждый час.

При истечении `check_status_until`:

- **Deposit** → принудительно `FAILED` с `DEPOSIT_NOT_PROCESSED_IN_TIME`.
- **Withdrawal** → прекращаем проверки, логируем `WITHDRAWAL_STUCK_IN_PROCESSING`.

Ключевая задача: `tasks.check_status(transaction_id)` — блокирует транзакцию, проверяет статус у провайдера, синхронизирует.

### 7. Проверить конкурентность

```python
# GOOD — блокировка перед обновлением
with transaction.atomic():
    trx = db_services.get_transaction(trx_id=trx_id, for_update=True)
    # ... изменения ...
    trx.save(update_fields=["status", "updated_at"])

# GOOD — Celery через on_commit
transaction.on_commit(
    lambda: tasks.check_status.delay(trx_id)
)

# BAD — HTTP внутри DB-транзакции
with transaction.atomic():
    trx = db_services.get_transaction(trx_id=trx_id, for_update=True)
    response = requests.post(provider_url)  # DEADLOCK RISK
```

### 8. Проверить аудит-логирование

Каждый значимый переход должен сопровождаться доменным аудитом:

```python
event_logs.create_transaction_log(
    trx_id=trx.id,
    event_type=EventType.CHARGE_BACK,
    description="Chargeback received, balance updated.",
    extra={
        "balance_transaction_id": str(balance_tx_record.id),
        "operational_before": str(balance_tx_record.operational_before),
        "operational_after": str(balance_tx_record.operational_after),
    },
)
```

**Не заменять** доменный аудит (`event_logs` / `PaymentTransactionEventLog`) обычными `logger`-вызовами.

### 9. Тесты и проверки

- Тесты: happy path + failure path — правила в `.agents/skills/django-testing/SKILL.md`.
- Проверки: таргетные тесты + `make mypy`; для критичных изменений статусной логики — полный набор.

## Жёсткие ограничения

- Не обновлять `PaymentTransaction.status` напрямую, кроме контролируемых service-сценариев `refund`/`chargeback`/`chargeback reversal` в transaction-processing.
- Не выполнять внешние HTTP-вызовы внутри открытой DB-транзакции.
- В Celery-задачи передавать идентификаторы (`trx_id`, `callback_id`), не ORM-объекты.
- Не пропускать балансовые side-effects при изменении статусных переходов.
- Не заменять `event_logs` обычными `logger`-вызовами для платежного аудита.
