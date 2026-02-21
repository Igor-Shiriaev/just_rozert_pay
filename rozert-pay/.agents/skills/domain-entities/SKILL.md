---
name: domain-entities
globs:
  - "rozert_pay/payment/models.py"
  - "rozert_pay/balances/models.py"
  - "rozert_pay/risk_lists/models.py"
  - "rozert_pay/account/models.py"
  - "rozert_pay/common/models.py"
  - "rozert_pay/limits/models/*.py"
  - "rozert_pay/payment_audit/models/*.py"
description: Доменная карта проекта — ключевые сущности, их роли, связи, неочевидные паттерны и ловушки. Использовать для понимания структуры данных перед работой с моделями. Точные поля и enum-значения читать из кода.
---

# Доменная карта rozert-pay

Этот скилл — высокоуровневая карта домена. Точные поля моделей и enum-значения **читай из кода** (`models.py`, `const.py`), здесь они не дублируются.

---

## Цепочка владения (ключевая иерархия)

```
MerchantGroup → Merchant → Wallet → CurrencyWallet → PaymentTransaction
                                ↓
                         PaymentSystem
```

Это главная ось проекта. Всё остальное привязано к элементам этой цепочки.

---

## Центральные сущности

### MerchantGroup / Merchant (`payment/models.py`)

Мерчант — клиент платформы. `MerchantGroup` группирует мерчантов под одним `User`.

**Что неочевидно**:

- `Merchant.save()` требует `reason_code` при изменении `operational_status`, иначе `ValueError`. Также принимает `comment` и `status_changed_by` для auditlog.
- `operational_status` определяет, может ли мерчант принимать платежи (`active` / `inactive` / `suspended` / `terminated`).
- `risk_status` (`white` / `grey` / `black`) — дублирует по смыслу `risk_control`, планируется переход на `risk_status`.
- Proxy-модель `MerchantProfile` — для отдельного admin-представления.

### PaymentSystem (`payment/models.py`)

Платёжная система (провайдер). Определяет TTL, IP-whitelist для callback, таймаут запроса.

Типы ПС (enum `PaymentSystemType`) — в `common/const.py`.

### Wallet / CurrencyWallet (`payment/models.py`)

`Wallet` — подключение мерчанта к ПС. Хранит зашифрованные `credentials` (EncryptedField).

`CurrencyWallet` — баланс конкретного кошелька в конкретной валюте. Unique constraint: (`wallet`, `currency`). Три баланса:
- `operational_balance` — все средства (confirmed + pending)
- `frozen_balance` — заморожено (withdrawal в процессе, rolling reserve)
- `pending_balance` — ожидает поступления от провайдера

`available_balance` — computed property: `operational − frozen − pending`.

**Deprecated**: поля `balance` и `hold_balance` — не использовать.

### PaymentTransaction (`payment/models.py`)

Центральная сущность — deposit или withdrawal. Статус меняется **только** через `sync_remote_status_with_transaction(...)`. Исключения: `refund`, `chargeback`, `chargeback reversal` в контролируемых service-сценариях (подробнее: `.agents/skills/payment-transaction-workflow/SKILL.md`).

**Что неочевидно**:
- Custom manager `PaymentTransactionManager` с методами `transactions_for_periodic_status_check()` и `for_system(system)`.
- Proxy-модель `TransactionManager` — для admin.
- Unique constraint: (`system_type`, `id_in_payment_system`).
- `extra` (JSONField) — хранит `user_data`, `form`, chargeback-флаги и другие per-system данные.

### Customer (`payment/models.py`)

Клиент мерчанта. PII зашифровано (`EncryptedFieldV2`), поиск — по детерминированным хешам (`DeterministicHashField` для email, phone). Идентифицируется по `external_id` (уникальный, от мерчанта).

---

## Финансовый аудит

### BalanceTransaction (`balances/models.py`)

Immutable ledger-запись о движении средств по `CurrencyWallet`. Каждая запись хранит снимки всех трёх балансов до/после операции. `amount` — signed (+ credit, − debit).

Типы операций (enum `BalanceTransactionType`) — в `balances/const.py`. Ключевые группы: стандартные операции, settlement flow, dispute & risk, ручные вмешательства.

### RollingReserveHold (`balances/models.py`)

Холдирование % от revenue на фиксированный срок. Привязан к двум `BalanceTransaction`: создание (`PROTECT`) и релиз (`SET_NULL`). Статусы: `ACTIVE` / `RELEASED`.

**Общее для `BalanceTransaction` и `RollingReserveHold`**: наследуются от `models.Model` (не `BaseDjangoModel`), используют UUID PK.

---

## Лимиты

### CustomerLimit / MerchantLimit (`limits/models/`)

Ограничения на операции — по количеству, суммам, процентам отклонений, burst-активности. Разделены по категориям: `risk`, `global_risk`, `business` (enum `LimitCategory`).

- `CustomerLimit` — привязан к `Customer`.
- `MerchantLimit` — привязан к `Merchant` или `Wallet` (определяется полем `scope`; `merchant` и `wallet` взаимоисключающие).

**Что неочевидно**:
- `CustomerLimit.save()` инвалидирует кэш лимитов.
- Proxy-модели с фильтрующими managers: `RiskCustomerLimit`, `BusinessCustomerLimit`, `RiskMerchantLimit`, `BusinessMerchantLimit`, `GlobalRiskMerchantLimit`.
- `decline_on_exceed` — автоматически отклоняет операцию при превышении.

### LimitAlert (`limits/models/limit_alert.py`)

Запись о срабатывании лимита. Привязан ровно к одному из `customer_limit` / `merchant_limit` + транзакции-триггеру. `is_critical` — computed property, делегирует в связанный лимит.

---

## Риск-листы

### RiskListEntry (`risk_lists/models.py`)

Запись в black/white/gray-листе. Матчинг по комбинации полей (`match_fields`): masked PAN, email, phone, IP. Proxy-модели: `WhiteListEntry`, `BlackListEntry`, `GrayListEntry`, `MerchantBlackListEntry`.

---

## Аудит операций

### DBAuditItem (`payment_audit/models/audit_item.py`)

Аудит-запись: привязывает `Wallet` + `PaymentTransaction` + статус операции + время. Unique: (`operation_time`, `transaction`).

---

## Callbacks

- `IncomingCallback` — входящий callback от ПС. Хранит body, headers, IP, статус обработки, данные об ошибке.
- `OutcomingCallback` — исходящий webhook мерчанту. Retry-логика: `max_attempts` (default=10), `current_attempt`.

---

## Вспомогательные модели (payment)

- `CustomerExternalPaymentSystemAccount` — аккаунт клиента в ПС
- `CustomerDepositInstruction` — инструкция для deposit
- `CustomerCard` — зашифрованная карта клиента
- `PaymentTransactionEventLog` / `EventLog` — аудит-логи
- `ACLGroup` — группа доступа (M2M: `MerchantGroup`, `Wallet`, `User`, `PaymentSystem`)
- `Bank`, `PaymentCardBank` — справочник банков и BIN-таблица
- `DepositAccount` — **legacy**, не использовать

---

## Паттерн миграции `*2`-полей

Многие модели содержат парные поля: `amount` (Decimal) + `amount2` (MoneyField), `currency` + `currency2`. Это переходный паттерн:

- `*2` — **новая версия**, предпочитать при чтении и записи.
- Decimal-поля — **legacy**.
- `save()` на `PaymentTransaction` и `BalanceTransaction` автоматически копирует legacy → `*2`, если `*2` is None.

---

## account app

### User (`account/models.py`)

`AbstractUser` с `USERNAME_FIELD = "email"`, поле `username` удалено.

---

## Полная карта связей

```
MerchantGroup (1) → (N) Merchant (1) → (N) Wallet (1) → (N) CurrencyWallet (1) → (N) PaymentTransaction
                                                  ↓
                                          PaymentSystem

Customer (1) → (N) PaymentTransaction
Customer (1) → (N) CustomerLimit → (N) LimitAlert
Merchant (1) → (N) MerchantLimit → (N) LimitAlert
Wallet   (1) → (N) MerchantLimit

PaymentTransaction → (N) BalanceTransaction
PaymentTransaction → (N) OutcomingCallback / IncomingCallback
PaymentTransaction → (N) PaymentTransactionEventLog / DBAuditItem / LimitAlert

CurrencyWallet → (N) BalanceTransaction / RollingReserveHold
Wallet         → (N) DBAuditItem
```

## Где искать

| Что нужно | Где смотреть |
|---|---|
| Поля и типы моделей | `rozert_pay/<app>/models.py` |
| Enum-значения | `rozert_pay/<app>/const.py`, `rozert_pay/common/const.py` |
| Платёжный флоу и статусы | `.agents/skills/payment-transaction-workflow/SKILL.md` |
| Правила для моделей | `.agents/skills/django-model-rules/SKILL.md` |
| Стиль кода | `.agents/skills/code-style/SKILL.md` |
