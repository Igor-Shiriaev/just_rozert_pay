# Cardpay Applepay Integration Design Document

## Общая информация

**Название интеграции:** `cardpay_applepay`
**Платежная система:** Cardpay (Apple Pay)
**Документация:** (внутренняя / предоставляется партнёром)

## Доступ и креденшалы

**Credentials (в wallet):**
- `terminal_code`
- `terminal_password`
- `callback_secret`
- `applepay_key`
- `applepay_certificate`

**Важно:** Секреты хранятся только в креденшалах, в код не добавляем.

## Deposit Flow

### Параметры запроса депозита (по коду)
- `payment_method`: `APPLEPAY`
- `payment_data.amount`, `payment_data.currency`
- `payment_data.encrypted_data` (из `extra.encrypted_data`)
- `customer` (email/locale/id)
- `merchant_order.id`
- `request.id`, `request.time`

### Flow депозита
1. Мерчант создаёт депозит через API.
2. Система создаёт транзакцию со статусом `PENDING` и сохраняет `encrypted_data`.
3. Отправляется запрос в Cardpay `/api/payments`.
4. Из ответа сохраняется `payment_data.id` в `id_in_payment_system`.
5. Запускается периодическая проверка статуса и обработка коллбэков.

## Withdraw Flow

### Источник `payment_data.id`
- Найти у пользователя последний успешный депозит через `cardpay_applepay`.
- Взять из него значение `payment_data.id` (хранится как `id_in_payment_system`).
- Подставить его в запрос на вывод в `payment_data.id`.

### Параметры запроса вывода
- `payment_method`: `BANKCARD`
- `payout_data.amount`, `payout_data.currency`, `payout_data.encrypted_data`
- `payment_data.id`: из последнего успешного депозита `cardpay_applepay`
- `card_account.recipient_info`: добавляется при включенном флаге `cardpay_applepay_card_account_field`
- `customer` (email/locale/id)
- `merchant_order.id`
- `request.id`, `request.time`

### Flow вывода
1. Мерчант создаёт транзакцию вывода через API.
2. Система ищет последний успешный депозит `cardpay_applepay` по этому пользователю.
3. Если найден `payment_data.id`, формирует запрос на вывод и отправляет в Cardpay `/api/payouts`.
4. Иначе транзакция выводится в статус `FAILED` (без обращения к платежке).
5. Запускается периодическая проверка статуса и обработка коллбэков.

## Callback обработка

- Статусы и `id_in_payment_system` берутся из `payment_data` для депозитов и `payout_data` для выводов.
- Используется единая логика Cardpay callback parsing.

## Структура интеграции

### Файлы (фактически в коде)
1. `rozert_pay/payment/systems/cardpay_systems/cardpay_applepay/`
   - `client.py` — формирование запросов и интеграция с Cardpay API
   - `controller.py` — логика транзакций и callback
   - `views.py` — endpoints `/api/payment/v1/cardpay-applepay/deposit|withdraw/`

2. Роуты:
   - `rozert_pay/payment/api_v1/urls.py`
   - коллбэк: `/api/payment/v1/rozert_cardpay_applepay/callback`

3. Тесты:
   - `tests/payment/systems/cardpay_systems/test_cardpay_applepay.py`

## Контекст для будущих итераций

- `payment_data.id` используется как связка «депозит → вывод».
- Для вывода Cardpay требуется `payment_method=BANKCARD` даже при Apple Pay.
- `card_account.recipient_info` добавляется по флагу `cardpay_applepay_card_account_field`.
