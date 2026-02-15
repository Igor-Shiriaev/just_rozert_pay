---
name: domain-entities
globs:
  - "rozert_pay/payment/models.py"
  - "rozert_pay/balances/models.py"
  - "rozert_pay/risk_lists/models.py"
  - "rozert_pay/account/models.py"
  - "rozert_pay/common/models.py"
description: Справочник доменных сущностей (Django-моделей) проекта — поля, связи, ключевые ограничения. Использовать когда нужно понять структуру данных или при работе с моделями.
---

# Доменные сущности rozert-pay

## Базовая модель

`BaseDjangoModel` (abstract, `common/models.py`): `id` BigAutoField + `created_at` + `updated_at`. Все новые модели наследуются от неё.

---

## payment app

### MerchantGroup

Группа мерчантов. Привязана к одному `User` (OneToOne).

| Поле | Тип | Примечание |
|---|---|---|
| `name` | CharField(200), unique | |
| `queue` | CharField(200), choices | Очередь обработки |
| `user` | OneToOne → `account.User` | |

### Merchant

Конкретный мерчант с API-ключом.

| Поле | Тип | Примечание |
|---|---|---|
| `uuid` | UUIDField, unique | Публичный идентификатор |
| `name` | CharField(200), unique | |
| `secret_key` | CharField(200), unique | API-ключ |
| `risk_control` | BooleanField | Включена ли проверка рисков |
| `sandbox` | BooleanField | Тестовый режим |
| `merchant_group` | FK → `MerchantGroup` | |
| `login_users` | M2M → `account.User` | Пользователи с доступом к админке |

### PaymentSystem

Платежная система (провайдер).

| Поле | Тип | Примечание |
|---|---|---|
| `name` | CharField(200), unique | |
| `slug` | CharField(200), unique | Машинное имя |
| `type` | CharField(200), choices | Тип ПС (из `SystemType`) |
| `is_active` | BooleanField | |
| `deposit_allowed_ttl_seconds` | PositiveIntegerField | TTL для deposit |
| `withdrawal_allowed_ttl_seconds` | PositiveIntegerField | TTL для withdrawal |
| `ip_whitelist` | ArrayField(CharField) | Разрешённые IP для callback |
| `ip_whitelist_enabled` | BooleanField | |
| `callback_secret_key` | CharField(200) | Ключ для верификации callback |
| `client_request_timeout` | FloatField, default=30 | Таймаут запроса к ПС |

### Wallet

Подключение мерчанта к платежной системе. Хранит credentials.

| Поле | Тип | Примечание |
|---|---|---|
| `uuid` | UUIDField, unique | Публичный идентификатор |
| `name` | CharField(200) | |
| `credentials` | EncryptedField(dict) | Зашифрованные учётные данные ПС |
| `default_callback_url` | URLField | URL для callback мерчанту |
| `allow_negative_balances` | BooleanField | Разрешить отрицательный баланс |
| `risk_control` | BooleanField | |
| `merchant` | FK → `Merchant` | |
| `system` | FK → `PaymentSystem` | |

### CurrencyWallet

Баланс кошелька в конкретной валюте. Unique constraint: (`wallet`, `currency`).

| Поле | Тип | Примечание |
|---|---|---|
| `currency` | CurrencyField | |
| `operational_balance` | MoneyField | Доступные средства |
| `frozen_balance` | MoneyField | Заморожено (withdrawal в процессе) |
| `pending_balance` | MoneyField | Ожидает подтверждения |
| `wallet` | FK → `Wallet` | |

Поля `balance` и `hold_balance` — **deprecated**, не использовать.

### Customer

Клиент мерчанта. PII зашифровано.

| Поле | Тип | Примечание |
|---|---|---|
| `uuid` | UUIDField, unique | |
| `external_id` | CharField(255), unique | ID в системе мерчанта |
| `language` | CharField(10) | |
| `risk_control` | BooleanField | |
| `email_encrypted` | EncryptedFieldV2 | |
| `email_deterministic_hash` | DeterministicHashField | Для поиска по email |
| `phone_encrypted` | EncryptedFieldV2 | |
| `phone_hash` | DeterministicHashField | Для поиска по phone |
| `extra_encrypted` | EncryptedFieldV2(JSON) | Дополнительные данные |

### PaymentTransaction

Центральная сущность — платежная транзакция. Стандартно статус меняется через `sync_remote_status_with_transaction`; исключения: `refund`, `chargeback`, `chargeback reversal` в контролируемых service-сценариях transaction-processing.

| Поле | Тип | Примечание |
|---|---|---|
| `uuid` | UUIDField, unique | Публичный идентификатор |
| `status` | CharField, choices | Из `TransactionStatus` |
| `type` | CharField(20), choices | `deposit` / `withdrawal` |
| `amount` | DecimalField(15,2) | Сумма |
| `amount2` | MoneyField | Сумма (MoneyField-версия) |
| `currency` / `currency2` | CurrencyField | Валюта |
| `callback_url` | URLField | URL для callback |
| `redirect_url` | URLField | URL редиректа клиента |
| `id_in_payment_system` | CharField(200) | ID транзакции в ПС |
| `decline_code` / `decline_reason` | CharField | Причина отказа |
| `extra` | JSONField | Доп. данные (chargeback-флаги и пр.) |
| `check_status_until` | DateTimeField | До какого момента проверять статус |
| `wallet` | FK → `CurrencyWallet` | |
| `customer` | FK → `Customer` (PROTECT) | |
| `customer_external_account` | FK → `CustomerExternalPaymentSystemAccount` (PROTECT) | |
| `customer_card` | FK → `CustomerCard` (PROTECT) | |

Unique constraint: (`system_type`, `id_in_payment_system`).

### IncomingCallback

Входящий callback от платежной системы.

| Поле | Тип | Примечание |
|---|---|---|
| `body` | TextField | Тело запроса |
| `headers` | JSONField | Заголовки |
| `ip` | GenericIPAddressField | IP источника |
| `status` | CharField, choices | Статус обработки |
| `error_type` / `error` / `traceback` | Text | Данные об ошибке |
| `remote_transaction_status` | JSONField | Статус от ПС |
| `system` | FK → `PaymentSystem` | |
| `transaction` | FK → `PaymentTransaction` | |

### OutcomingCallback

Исходящий webhook мерчанту.

| Поле | Тип | Примечание |
|---|---|---|
| `callback_type` | CharField, choices | Тип callback |
| `target` | URLField | URL мерчанта |
| `body` | JSONField | Тело |
| `status` | CharField, choices | pending / sent / failed |
| `max_attempts` | PositiveIntegerField, default=10 | |
| `current_attempt` | PositiveIntegerField | |
| `transaction` | FK → `PaymentTransaction` | |

### Вспомогательные модели (payment)

- `CustomerExternalPaymentSystemAccount` — аккаунт клиента в ПС (unique: `system_type` + `wallet` + `unique_account_number`)
- `CustomerDepositInstruction` — инструкция для deposit (unique: `system_type` + `deposit_account_number`)
- `CustomerCard` — карта клиента (зашифрована, unique: `unique_identity` + `customer`)
- `PaymentTransactionEventLog` — аудит-лог событий транзакции
- `EventLog` — общий лог событий
- `ACLGroup` — группа доступа (связывает `MerchantGroup`, `Wallet`, `User`, `PaymentSystem`)
- `DepositAccount` — депозитный аккаунт (legacy)
- `Bank`, `PaymentCardBank` — справочник банков и BIN-таблица

---

## balances app

### BalanceTransaction

Запись движения средств по `CurrencyWallet`. Аудит-лог всех балансовых операций.

| Поле | Тип | Примечание |
|---|---|---|
| `id` | UUIDField, PK | |
| `type` | CharField, choices | Из `BalanceTransactionType` |
| `amount` / `amount2` | Decimal / MoneyField | Сумма операции |
| `operational_before` / `operational_after` | Decimal + MoneyField | Снимок operational-баланса |
| `frozen_before` / `frozen_after` | Decimal + MoneyField | Снимок frozen-баланса |
| `pending_before` / `pending_after` | Decimal + MoneyField | Снимок pending-баланса |
| `initiator` | CharField, choices | Кто инициировал |
| `currency_wallet` | FK → `CurrencyWallet` (PROTECT) | |
| `payment_transaction` | FK → `PaymentTransaction` (SET_NULL) | |

### RollingReserveHold

Холдирование средств на rolling reserve.

| Поле | Тип | Примечание |
|---|---|---|
| `id` | UUIDField, PK | |
| `amount` | MoneyField | Сумма холда |
| `hold_until` | DateTimeField | Дата релиза |
| `status` | CharField, choices | active / released |
| `currency_wallet` | FK → `CurrencyWallet` (PROTECT) | |
| `source_transaction` | FK → `BalanceTransaction` (PROTECT) | Транзакция создания холда |
| `release_transaction` | FK → `BalanceTransaction` (SET_NULL) | Транзакция релиза |

---

## risk_lists app

### RiskListEntry

Запись в risk-листе. Proxy-модели: `WhiteListEntry`, `BlackListEntry`, `GrayListEntry`, `MerchantBlackListEntry`.

| Поле | Тип | Примечание |
|---|---|---|
| `list_type` | CharField(16), choices | white / black / gray |
| `scope` | CharField(10), choices | |
| `operation_type` | CharField(10), choices | deposit / withdrawal |
| `match_fields` | ArrayField(CharField) | По каким полям матчить |
| `masked_pan` / `email` / `phone` / `ip` | Различные | Критерии сопоставления |
| `customer` | FK → `Customer` | |
| `wallet` | FK → `Wallet` | |
| `merchant` | FK → `Merchant` | |
| `transaction` | FK → `PaymentTransaction` | Транзакция-причина |
| `added_by` | FK → `User` | |

---

## account app

### User

Расширение `AbstractUser`. `USERNAME_FIELD = "email"`, поле `username` удалено.

---

## Ключевые связи (цепочка владения)

```
MerchantGroup (1) → (N) Merchant (1) → (N) Wallet (1) → (N) CurrencyWallet (1) → (N) PaymentTransaction
                                                  ↓
                                          PaymentSystem
Customer (1) → (N) PaymentTransaction
Customer (1) → (N) CustomerExternalPaymentSystemAccount
Customer (1) → (N) CustomerCard

PaymentTransaction (1) → (N) BalanceTransaction
PaymentTransaction (1) → (N) OutcomingCallback
PaymentTransaction (1) → (N) IncomingCallback (через system)
PaymentTransaction (1) → (N) PaymentTransactionEventLog
```
