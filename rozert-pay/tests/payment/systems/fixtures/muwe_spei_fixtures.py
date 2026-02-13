MUWE_BASE_URL = "https://test.sipelatam.mx"
CURRENCY = "MXN"
AMOUNT = 100.00  # MXN
AMOUNT_CENTAVOS = 10000  # In centavos (MUWE format)

# Test CLABEs (valid with correct check digits)
CLABE1 = "646180157000000004"  # Customer deposit CLABE
CLABE2 = "012180001234567897"  # Another customer CLABE
SENDER_CLABE = "002115016003269411"  # Sender's bank account (valid CLABE)

# Test IDs
FOREIGN_ID_DEPOSIT = "P2025120193442976058023936"  # MUWE order ID for deposit
FOREIGN_ID_WITHDRAWAL = "P2025120193442976058099999"  # MUWE order ID for withdrawal
MCH_ORDER_NO = "CSMOSIPE25120522114307734443"  # Merchant order number

# MUWE credentials (fake for testing)
MUWE_APP_ID = "fake_app_id_12345"
MUWE_MCH_ID = "fake_mch_id_67890"
MUWE_API_KEY = "fake_api_key_abc123xyz456def"

# Test bank code
BANK_CODE = "40014"
SENDER_NAME = "TEST USER DEBUG"

# Clave Rastreo (tracking key)
IDENTIFIER = "2025120440014TRAPP000428410530"


# =============================================================================
# API RESPONSES
# =============================================================================

# Response from MUWE API when creating deposit instruction (getting CLABE)
# According to /api/unified/collection/create documentation
MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE = {
    "mchId": 67890,  # Fake merchant ID as integer
    "nonceStr": "testNonceCreate123",
    "reference": CLABE1,  # CLABE for customer deposits
    "resCode": "SUCCESS",
    "sign": "CALCULATED_SIGNATURE",
    "token": "test_token_abc123",
    "url": "https://test.sipelatam.mx/deposit/test_token_abc123",
}

MUWE_CREATE_INSTRUCTION_SUCCESS_RESPONSE2 = {
    "mchId": 67890,
    "nonceStr": "testNonceCreate456",
    "reference": CLABE2,
    "resCode": "SUCCESS",
    "sign": "CALCULATED_SIGNATURE",
    "token": "test_token_def456",
    "url": "https://test.sipelatam.mx/deposit/test_token_def456",
}

# Response from MUWE API when initiating withdrawal
MUWE_WITHDRAWAL_INIT_SUCCESS_RESPONSE = {
    "resCode": "SUCCESS",
    "resMsg": "success",
    "orderId": FOREIGN_ID_WITHDRAWAL,
    "mchOrderNo": "test-withdrawal-uuid",
    "amount": AMOUNT_CENTAVOS,
    "fee": 10,  # Fee in centavos
}

# =============================================================================
# WEBHOOKS (Incoming Callbacks)
# =============================================================================

# Deposit success webhook (customer made a deposit)
MUWE_DEPOSIT_SUCCESS_WEBHOOK = {
    "income": AMOUNT_CENTAVOS,  # Amount received in centavos
    "bankCode": BANK_CODE,
    "identifier": IDENTIFIER,
    "amount": AMOUNT_CENTAVOS,
    "mchId": MUWE_MCH_ID,
    "orderId": FOREIGN_ID_DEPOSIT,
    "accountName": SENDER_NAME,
    "mchOrderNo": MCH_ORDER_NO,
    "fee": 0,
    "channelOrderNo": "test-channel-order-001",
    "nonceStr": "testNonce123456",
    "reference": CLABE1,  # Customer's CLABE
    "appId": MUWE_APP_ID,
    "accountNo": SENDER_CLABE,  # Sender's bank account
    "successTime": 1733341200000,  # Unix timestamp in milliseconds
    "status": 2,  # 2 = SUCCESS
    "sign": "CALCULATED_SIGNATURE",  # Will be calculated in tests
}

# Deposit success webhook without bankCode (MUWE sometimes omits it)
MUWE_DEPOSIT_SUCCESS_WEBHOOK_NO_BANK_CODE = {
    k: v for k, v in MUWE_DEPOSIT_SUCCESS_WEBHOOK.items() if k != "bankCode"
}

# Deposit failed webhook (deposit failed)
MUWE_DEPOSIT_FAILED_WEBHOOK = {
    "income": 0,  # No amount credited
    "bankCode": BANK_CODE,
    "identifier": IDENTIFIER,
    "amount": AMOUNT_CENTAVOS,
    "mchId": MUWE_MCH_ID,
    "orderId": "P2025120193442976058023937",  # Different order ID
    "accountName": SENDER_NAME,
    "mchOrderNo": MCH_ORDER_NO,
    "fee": 0,
    "channelOrderNo": "test-channel-order-002",
    "nonceStr": "testNonce123457",
    "reference": CLABE1,
    "appId": MUWE_APP_ID,
    "accountNo": SENDER_CLABE,
    "successTime": 1733341200000,
    "status": 3,  # 3 = FAILED
    "errCode": "40008",
    "errMsg": "accountNo or accountName is invalid",
    "sign": "CALCULATED_SIGNATURE",
}

# Withdrawal success webhook
MUWE_WITHDRAWAL_SUCCESS_WEBHOOK = {
    "amount": AMOUNT_CENTAVOS,
    "appId": MUWE_APP_ID,
    "fee": 10,
    "identifier": "G2025071944642279492419584",
    "mchId": MUWE_MCH_ID,
    "mchOrderNo": "test-withdrawal-uuid",  # Transaction UUID
    "orderId": FOREIGN_ID_WITHDRAWAL,
    "status": 2,  # 2 = SUCCESS
    "nonceStr": "testNonce789012",
    "sign": "CALCULATED_SIGNATURE",
}

# Withdrawal failed webhook
MUWE_WITHDRAWAL_FAILED_WEBHOOK = {
    "amount": AMOUNT_CENTAVOS,
    "appId": MUWE_APP_ID,
    "fee": 10,
    "identifier": "G2025071944642279492419584",
    "mchId": MUWE_MCH_ID,
    "mchOrderNo": "test-withdrawal-uuid",
    "orderId": FOREIGN_ID_WITHDRAWAL,
    "status": 3,  # 3 = FAILED
    "errMsgCode": "40003",  # MUWE error code: pay out not sufficient funds
    "errMsg": "pay out not sufficient funds",
    "nonceStr": "testNonce789013",
    "sign": "CALCULATED_SIGNATURE",
}

# Ping webhook (health check from MUWE)
MUWE_PING_WEBHOOK = {
    "event": "notify.ping",
    "appId": MUWE_APP_ID,
    "mchId": MUWE_MCH_ID,
    "nonceStr": "testNoncePing",
    "sign": "CALCULATED_SIGNATURE",
}
