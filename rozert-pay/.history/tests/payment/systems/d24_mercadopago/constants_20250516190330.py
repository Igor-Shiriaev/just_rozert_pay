DEPOSIT_BASE_URL = "https://deposit.api"
WITHDRAWAL_AND_STATUS_BASE_URL = "https://remain.api"
CURRENCY = "MXN"
DEPOSIT_FOREIGN_ID = "301524253"
DEPOSIT_FOREIGN_ID2 = "deposit_foreign_id2"
WITHDRAWAL_FOREIGN_ID = "withdrawal_foreign_id"
AMOUNT = "2333.71"
CURRENCY = "MXN"
MEXICAN_VALID_CURP = "ssss001230mlllllj0"
MEXICAN_VALID_CURP2 = "ssss911230mlllllj0"
INVALID_MEXICAN_CURP = "ssss101210mlllllj0"
VALID_CLABE = "021790064060296642"
INVALID_CLABE = "021790064060296643"

D24_MERCADO_PAGO_DEPOSIT_FAILED_RESPONSE = {
    "code": 418,
    "description": "Missing required fields in order to generate Deposit",
    "type": "MISSING_REQUIRED_FIELDS",
}


D24_MERCADO_PAGO_WITHDRAWAL_FAILED_RESPONSE = {
    "code": 303,
    "message": "bankAccount: Invalid or missing Bank account;Invalid bank code",
    "reason": "Invalid bank code",
}


D24_MERCADO_PAGO_DEPOSIT_SUCCESS_RESPONSE = {
    "checkout_type": "ONE_SHOT",
    "redirect_url": "https://payment-stg.depositcheckout.com/v1/checkout/eyJhbGciOiJIUzM4NCJ9.eyJqdGkiOiI1NzE4MjMzMiIsImlhdCI6MTc0MDIxMjM1MCwiZXhwIjoxNzQxNTA4MzUwLCJsYW5ndWFnZSI6ImVzIn0.ucf2BY2jZY9brgZdj4tRvI_1cwSgOOcCaRdWezOmvA5wnb7bAU-HgNTg_KTtcfPl/MX/ME/3541/19502",
    "iframe": True,
    "deposit_id": DEPOSIT_FOREIGN_ID,
    "user_id": "62dd744c-cbfa-4357-8ef0-460390e78b5c",
    "merchant_invoice_id": "postmanTest907958248",
    "payment_info": {
        "type": "VOUCHER",
        "payment_method": "ME",
        "payment_method_name": "Mercado Pago Mexico",
        "amount": AMOUNT,
        "currency": CURRENCY,
        "expiration_date": "2025-02-22 20:19:10",
        "created_at": "2025-02-22 08:19:10",
        "metadata": {
            "reference": "57182332",
            "payment_method_code": "ME",
            "enabled_redirect": True,
        },
    },
}

D24_MERCADO_PAGO_DEPOSIT_CALLBACK = {
    "invoice_id": "800000001",
    "deposit_id": DEPOSIT_FOREIGN_ID,
    "amount": AMOUNT,
    "country": "BR",
    "currency": CURRENCY,
    "payer": {
        "id": "11111",
        "document": "84932568207",
        "document_type": "CPF",
        "email": "johnSmith12@hotmail.com",
        "first_name": "John",
        "last_name": "Smith",
        "phone": "+233852662222",
        "birth_date": "19880910",
        "address": {
            "street": "Calle 13",
            "city": "bahia",
            "state": "SP",
            "zip_code": "12345-678",
        },
    },
    "credit_card": {
        "cvv": "123",
        "card_number": "4111111111111111",
        "expiration_month": "10",
        "expiration_year": "25",
        "holder_name": "JOHN SMITH",
    },
    "three_domain_secure": {
        "cavv": "AJkBARglcgAAAAPohABHdQAAAAA=",
        "eci": "05",
        "transaction_id": "7e76d057-100a-4d0d-9683-5eb0ce0ee3a4",
        "specification_version": "2.0.0",
    },
    "description": "Test transaction",
    "client_ip": "123.123.123.123",
    "device_id": "knakvuejffkiebyab",
    "fee_on_payer": False,
}


D24_MERCADO_PAGO_DEPOSIT_GET_STATUS_PENDING_RESPONSE = {
    "user_id": "62dd744c-cbfa-4357-8ef0-460390e78b5c",
    "deposit_id": DEPOSIT_FOREIGN_ID,
    "invoice_id": "postmanTest195345392",
    "country": "MX",
    "currency": "MXN",
    "usd_amount": 4.83,
    "local_amount": 100.00,
    "payment_method": "ME",
    "payment_type": "VOUCHER",
    "status": "PENDING",
    "payer": {
        "document": "ssss001230mlllllj0",
        "document_type": "CURP",
        "email": "test0@example.com",
        "first_name": "John",
        "last_name": "Doe",
    },
    "fee_amount": 0.24,
    "fee_currency": "USD",
    "refunded": False,
    "current_payer_verification": "NO_CURRENT_PAYER_DATA",
}


D24_MERCADO_PAGO_DEPOSIT_GET_STATUS_SUCCESS_RESPONSE = {
    "user_id": "62dd744c-cbfa-4357-8ef0-460390e78b5c",
    "deposit_id": DEPOSIT_FOREIGN_ID,
    "invoice_id": "postmanTest531641621",
    "country": "MX",
    "currency": CURRENCY,
    "usd_amount": 4.84,
    "local_amount": 100.00,
    "payment_method": "ME",
    "payment_type": "VOUCHER",
    "status": "COMPLETED",
    "payer": {
        "document": "ssss001230mlllllj0",
        "document_type": "CURP",
        "email": "test0@example.com",
        "first_name": "John",
        "last_name": "Doe",
    },
    "fee_amount": 0.24,
    "fee_currency": "USD",
    "refunded": False,
    "current_payer_verification": "NO_CURRENT_PAYER_DATA",
    "completed_payment_method_code": "ME",
}


D24_MERCADO_PAGO_DEPOSIT_GET_STATUS_FAILED_RESPONSE = {
    "user_id": "62dd744c-cbfa-4357-8ef0-460390e78b5c",
    "deposit_id": DEPOSIT_FOREIGN_ID,
    "invoice_id": "postmanTest547394843",
    "country": "MX",
    "currency": CURRENCY,
    "usd_amount": 48.39,
    "local_amount": AMOUNT,
    "payment_method": "ME",
    "payment_type": "VOUCHER",
    "status": "EXPIRED",
    "payer": {
        "document": MEXICAN_VALID_CURP,
        "document_type": "CURP",
        "email": "test0@example.com",
        "first_name": "John",
        "last_name": "Doe",
    },
    "fee_amount": 2.40,
    "fee_currency": "USD",
    "refunded": False,
    "current_payer_verification": "NO_CURRENT_PAYER_DATA",
}


D24_MERCADO_PAGO_WITHDRAWAL_SUCCESS_RESPONSE = {"cashout_id": WITHDRAWAL_FOREIGN_ID}

D24_MERCADO_PAGO_WITHDRAWAL_CALLBACK = (
    "date=2020-03-12%2020%3A26%3A11"
    "&bank_reference_id="
    "&comments="
    "&external_id={trx_uuid_placeholder}"
    "&control=A4CFF64E78C4BD01F8BFCA4AFF04632EC4A33CC61BD6BBD156BA1289897892EB"
    f"&cashout_id={WITHDRAWAL_FOREIGN_ID}"
    "&status_reason="
)

D24_MERCADO_PAGO_WITHDRAWAL_GET_STATUS_SUCCESS_RESPONSE = {
    "cashout_status": 1,
    "cashout_status_description": "Completed",
}

D24_MERCADO_PAGO_WITHDRAWAL_GET_STATUS_FAILED_RESPONSE = {
    "cashout_status": 3,
    "cashout_status_description": "Rejected",
    "rejection_code": 101,
    "rejection_reason": "Test",
}

D24_MERCADO_PAGO_WITHDRAWAL_GET_STATUS_PENDING_RESPONSE = {
    "cashout_status": 0,
    "cashout_status_description": "Pending",
}

D24_MERCADO_PAGO_WITHDRAWAL_GET_STATUS_NOT_FOUND_RESPONSE = {
    "code": 509,
    "message": "Cashout not found with this ID",
}
