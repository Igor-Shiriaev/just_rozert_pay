# Constants for M-Pesa MZ tests

BASE_URL = "https://api.mpesa.vm.co.mz"
CURRENCY = "MZN"
DEPOSIT_FOREIGN_ID = "mpesa_deposit_12345"
WITHDRAWAL_FOREIGN_ID = "mpesa_withdrawal_12345"
AMOUNT = "100.00"
PHONE_NUMBER = "258841234567"

MPESA_MZ_DEPOSIT_SUCCESS_RESPONSE = {
    "output_ResponseCode": "INS-0",
    "output_ResponseDesc": "Request processed successfully",
    "output_TransactionID": DEPOSIT_FOREIGN_ID,
    "output_ConversationID": "test_conversation_id",
}

MPESA_MZ_DEPOSIT_FAILED_RESPONSE = {
    "output_ResponseCode": "INS-1",
    "output_ResponseDesc": "Invalid request",
}

MPESA_MZ_DEPOSIT_CALLBACK = {
    "output_ResponseCode": "INS-0",
    "output_ResponseDesc": "Request processed successfully",
    "output_TransactionID": DEPOSIT_FOREIGN_ID,
    "output_ThirdPartyReference": "",  # Will be filled with transaction UUID in test
    "output_ResponseTransactionStatus": "Success",
}

MPESA_MZ_DEPOSIT_GET_STATUS_SUCCESS_RESPONSE = {
    "output_ResponseCode": "INS-0",
    "output_ResponseDesc": "Request processed successfully",
    "output_ResponseTransactionStatus": "Success",
    "output_TransactionID": DEPOSIT_FOREIGN_ID,
}

MPESA_MZ_DEPOSIT_GET_STATUS_PENDING_RESPONSE = {
    "output_ResponseCode": "INS-0",
    "output_ResponseDesc": "Request processed successfully",
    "output_ResponseTransactionStatus": "Pending",
    "output_TransactionID": DEPOSIT_FOREIGN_ID,
}

MPESA_MZ_WITHDRAWAL_SUCCESS_RESPONSE = {
    "output_ResponseCode": "INS-0",
    "output_ResponseDesc": "Request processed successfully",
    "output_TransactionID": WITHDRAWAL_FOREIGN_ID,
    "output_ConversationID": "test_conversation_id",
}

MPESA_MZ_WITHDRAWAL_FAILED_RESPONSE = {
    "output_ResponseCode": "INS-1",
    "output_ResponseDesc": "Invalid request",
}

MPESA_MZ_WITHDRAWAL_CALLBACK = {
    "output_ResponseCode": "INS-0",
    "output_ResponseDesc": "Request processed successfully",
    "output_TransactionID": WITHDRAWAL_FOREIGN_ID,
    "output_ThirdPartyReference": "",  # Will be filled with transaction UUID in test
    "output_ResponseTransactionStatus": "Success",
}

MPESA_MZ_WITHDRAWAL_GET_STATUS_SUCCESS_RESPONSE = {
    "output_ResponseCode": "INS-0",
    "output_ResponseDesc": "Request processed successfully",
    "output_ResponseTransactionStatus": "Success",
    "output_TransactionID": WITHDRAWAL_FOREIGN_ID,
}

MPESA_MZ_PUBLIC_KEY_SAMPLE = "MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAszE+xAKVB9HRarr6/uHYYAX/RdD6KGVIGlHv98QKDIH26ldYJQ7zOuo9qEscO0M1psSPe/67AWYLEXh13fbtcSKGP6WFjT9OY6uV5ykw9508x1sW8UQ4ZhTRNrlNsKizE/glkBfcF2lwDXJGQennwgickWz7VN+AP/1c4DnMDfcl8iVIDlsbudFoXQh5aLCYl+XOMt/vls5a479PLMkPcZPOgMTCYTCE6ReX3KD2aGQ62uiu2T4mK+7Z6yvKvhPRF2fTKI+zOFWly//IYlyB+sde42cIU/588msUmgr3G9FYyN2vKPVy/MhIZpiFyVc3vuAAJ/mzue5p/G329wzgcz0ztyluMNAGUL9A4ZiFcKOebT6y6IgIMBeEkTwyhsxRHMFXlQRgTAufaO5hiR/usBMkoazJ6XrGJB8UadjH2m2+kdJIieI4FbjzCiDWKmuM58rllNWdBZK0XVHNsxmBy7yhYw3aAIhFS0fNEuSmKTfFpJFMBzIQYbdTgI28rZPAxVEDdRaypUqBMCq4OstCxgGvR3Dy1eJDjlkuiWK9Y9RGKF8HOI5a4ruHyLheddZxsUihziPF9jKTknsTZtF99eKTIjhV7qfTzxXq+8GGoCEABIyu26LZuL8X12bFqtwLAcjfjoB7HlRHtPszv6PJ0482ofWmeH0BE8om7VrSGxsCAwEAAQ=="
MPESA_MZ_API_KEY_SAMPLE = "aaaab09uz9f3asdcjyk7els777ihmwv8"
MPESA_MZ_BEARER_SAMPLE = "rfNjFso4uJbzhwl8E9vizqmHEuD7XDmPqfsRx1L62UoTmURGGLAGgJSl9lCPbgy03Q7NwozFYD4r9BFQY5QpvErHximBDU8HE25urVahm0HnB8VyCIobs684XGSN4GjdequePDrG6xUAxxpvmhqZRlGt1tUjUBeBg6kYqp4EnKHsiaBtvd0THGLZbefpT6UaShASQWYNiEPwEon5wtUMaDwnyQEazDu1H2ieN3r8cCVM3hsak59J/1MP07FQjdFbxdCLfA0DuxgpeKpvLs7WrA767WJSB1QZy7hcP1igSGRfd7Zrp6E7gIukdpC0DApqPKa4XsNTo2AMpG4AwiET2WeKvHn539gbwREXf79kZlYdFDCgTc0Zs7OfDx5ZXMCBKHOS/H3tVFJqXTfEfIF5LOzrFU5pPE0HeNBV0Q2vm8qRwQX0RijnvMOGpdcmXb0qoph4oy8Mj+vjRfFRboMAafttDozBhRmWEmeBB3EjYASm1fToQp5ey6ltCiEt8rjL5PlexxB0u3u2LVJQcDzMVNiiq10t1xyw8qtc6BMOyrKVlIANWglRYOKr9saVBVvDFUcCfsghMjUTDeAwHom4A3cSDWmVlNF9Vs/WqCoUzjQCV0BFPDzeAUbQqt7h7OgFno/+D9n5j1eMro0aXbbHNx71u8YmgPJhdixzFhxM1Pw="

MPESA_PARSED_DUPLICATE_TRANSACTION_DEPOSIT_RESPONSE = {
    "success": False,
    "status": {"code": "INS-10", "description": "Duplicate Transaction"},
    "data": {"conversation": "abf65838b4b04bb284781c9cdefbe3b5", "reference": "11114"},
}


MPESA_PARSED_SUCCESS_DEPOSIT_RESPONSE = {
    "success": True,
    "status": {"code": "INS-0", "description": "Successfully Accepted Request"},
    "data": {
        "conversation": "6c9f6438770b4fe2acbfffa11d793040",
        "reference": "3202e4a4",
    },
}
