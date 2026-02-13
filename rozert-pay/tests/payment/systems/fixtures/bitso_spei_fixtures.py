import typing as ty

from rozert_pay.payment.systems.bitso_spei import bitso_spei_const

BITSO_SPEI_BASE_URL = "https://bitsospei"
CURRENCY_FOREIGN = "MXN"
AMOUNT_FOREIGN = 120
FOREIGN_ID = "c5b8d7f0768ee91d3b33bee648318688"
FOREIGN_ID2 = "c5b8d7f0768ee91d3b33b44648318688"
CLABE1 = "710969000012345678"
CLABE2 = "710969000012345622"
SENDER_CLABE = "012180044451188599"
SENDER_CLABE_DEBIT_CARD = "0121800444511885"
CLAVE_RASTREO = "MBAN01002412260074384299"

BITSO_SPEI_GET_CLABE1_SUCCESS_RESPONSE = {
    "payload": {
        "clabe": CLABE1,
        "created_at": "2024-10-25T14:38:45",
        "deposit_minimum_amount": None,
        "status": "ENABLED",
        "type": "ADDITIONAL_INTERNATIONAL",
        "updated_at": None,
    },
    "success": True,
}

BITSO_SPEI_GET_CLABE2_SUCCESS_RESPONSE = {
    "payload": {
        "clabe": CLABE2,
        "created_at": "2024-10-25T14:38:45",
        "deposit_minimum_amount": None,
        "status": "ENABLED",
        "type": "ADDITIONAL_INTERNATIONAL",
        "updated_at": None,
    },
    "success": True,
}

BITSO_SPEI_DEPOSIT_SUCCESS_CALLBACK = {
    "event": "funding",
    "payload": {
        "fid": FOREIGN_ID,
        "status": "complete",
        "created_at": "2024-12-25T14:04:46+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "praxis",
        "method_name": "SPEI Transfer",
        "amount": AMOUNT_FOREIGN,
        "asset": CURRENCY_FOREIGN.lower(),
        "network": "spei",
        "protocol": "clabe",
        "integration": "praxis",
        "details": {
            "sender_name": "MARIO PIu00a5A                 ",
            "sender_clabe": SENDER_CLABE,
            "receive_clabe": CLABE1,
            "sender_bank": 40012,
            "clave": 7702553,
            "clave_rastreo": CLAVE_RASTREO,
            "numeric_reference": "1712240",
            "concepto": "test 2512",
            "cep_link": "",
            "sender_rfc_curp": "DUPM920620C22",
            "deposit_type": "third_party",
        },
    },
}

BITSO_SPEI_DEPOSIT_SUCCESS_CALLBACK2 = {
    "event": "funding",
    "payload": {
        "fid": FOREIGN_ID2,
        "status": "complete",
        "created_at": "2024-12-25T14:04:46+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "praxis",
        "method_name": "SPEI Transfer",
        "amount": "100",
        "asset": CURRENCY_FOREIGN.lower(),
        "network": "spei",
        "protocol": "clabe",
        "integration": "praxis",
        "details": {
            "sender_name": "MARIO PIu00a5A                 ",
            "sender_clabe": "",
            "receive_clabe": "",
            "sender_bank": 40012,
            "clave": 7702553,
            "clave_rastreo": CLAVE_RASTREO,
            "numeric_reference": "1712240",
            "concepto": "test 2512",
            "cep_link": "",
            "sender_rfc_curp": "DUPM920620C22",
            "deposit_type": "third_party",
        },
    },
}

BITSO_SPEI_WITHDRAWAL_GET_STATUS_SUCCESS_RESPONSE = {
    "success": True,
    "payload": [
        {
            "fid": FOREIGN_ID,
            "status": "complete",
            "created_at": "2022-12-08T17:52:31.000+00:00",
            "currency": CURRENCY_FOREIGN.lower(),
            "method": CURRENCY_FOREIGN.lower(),
            "method_name": "Bitcoin Network",
            "amount": "100",
            "asset": CURRENCY_FOREIGN.lower(),
            "network": CURRENCY_FOREIGN.lower(),
            "protocol": CURRENCY_FOREIGN.lower(),
            "integration": "bitgo-v2",
            "details": {
                "tx_hash": "*******4693e9fb5fffcaf730c11f32d1922e5837f76ca82189d3b**********",
                "clave_de_rastreo": CLAVE_RASTREO,
            },
        }
    ],
}

BITSO_SPEI_DEPOSIT_GET_STATUS_SUCCESS_RESPONSE = {
    "success": True,
    "payload": [
        {
            "fid": FOREIGN_ID,
            "status": "complete",
            "created_at": "2022-12-08T17:52:31.000+00:00",
            "currency": CURRENCY_FOREIGN.lower(),
            "method": CURRENCY_FOREIGN.lower(),
            "method_name": "Bitcoin Network",
            "amount": AMOUNT_FOREIGN,
            "asset": CURRENCY_FOREIGN.lower(),
            "network": CURRENCY_FOREIGN.lower(),
            "protocol": CURRENCY_FOREIGN.lower(),
            "integration": "bitgo-v2",
            "details": {
                "tx_hash": "*******4693e9fb5fffcaf730c11f32d1922e5837f76ca82189d3b**********",
                "clave_rastreo": CLAVE_RASTREO,
            },
        }
    ],
}

BITSO_SPEI_DEPOSIT_GET_STATUS_SUCCESS_RESPONSE2 = {
    "success": True,
    "payload": [
        {
            "fid": FOREIGN_ID,
            "status": "complete",
            "created_at": "2022-12-08T17:52:31.000+00:00",
            "currency": CURRENCY_FOREIGN.lower(),
            "method": CURRENCY_FOREIGN.lower(),
            "method_name": "Bitcoin Network",
            "amount": "100",
            "asset": CURRENCY_FOREIGN.lower(),
            "network": CURRENCY_FOREIGN.lower(),
            "protocol": CURRENCY_FOREIGN.lower(),
            "integration": "bitgo-v2",
            "details": {
                "tx_hash": "*******4693e9fb5fffcaf730c11f32d1922e5837f76ca82189d3b**********",
                "clave_rastreo": CLAVE_RASTREO,
            },
        }
    ],
}

BITSO_SPEI_GET_STATUS_PENDING_RESPONSE = {
    "success": True,
    "payload": [
        {
            "fid": FOREIGN_ID,
            "status": "pending",
            "created_at": "2022-12-08T17:52:31.000+00:00",
            "currency": CURRENCY_FOREIGN.lower(),
            "method": CURRENCY_FOREIGN.lower(),
            "method_name": "Bitcoin Network",
            "amount": AMOUNT_FOREIGN,
            "asset": CURRENCY_FOREIGN.lower(),
            "network": CURRENCY_FOREIGN.lower(),
            "protocol": CURRENCY_FOREIGN.lower(),
            "integration": "bitgo-v2",
            "details": {
                "tx_hash": "*******4693e9fb5fffcaf730c11f32d1922e5837f76ca82189d3b**********"
            },
        }
    ],
}

BITSO_SPEI_GET_STATUS_FAILED_RESPONSE = {
    "success": True,
    "payload": [
        {
            "fid": FOREIGN_ID,
            "status": "failed",
            "created_at": "2022-12-08T17:52:31.000+00:00",
            "currency": CURRENCY_FOREIGN.lower(),
            "method": CURRENCY_FOREIGN.lower(),
            "method_name": "Bitcoin Network",
            "amount": AMOUNT_FOREIGN,
            "asset": CURRENCY_FOREIGN.lower(),
            "protocol": CURRENCY_FOREIGN.lower(),
            "integration": "bitgo-v2",
            "details": {
                "tx_hash": "*******4693e9fb5fffcaf730c11f32d1922e5837f76ca82189d3b**********",
                "fail_reason": bitso_spei_const.DECLINE_CODES[0],
            },
        }
    ],
}

BITSO_SPEI_GET_STATUS_FAILED_RESPONSE2 = {
    "error": {
        "code": "0602",
        "message": "The withdrawal exceeds the available balance. Please add more funds to continue.",
    },
    "success": False,
}

BITSO_SPEI_GET_STATUS_FAILED_RESPONSE3 = {
    "success": True,
    "payload": [
        {
            "wid": FOREIGN_ID,
            "status": "complete",
            "created_at": "2025-01-20T18:25:07+00:00",
            "currency": CURRENCY_FOREIGN.lower(),
            "method": "praxis",
            "method_name": "SPEI Transfer",
            "amount": AMOUNT_FOREIGN,
            "asset": CURRENCY_FOREIGN.lower(),
            "network": "spei",
            "protocol": "clabe",
            "integration": "praxis",
            "details": {
                "fail_reason": "Excede el límite de abonos permitidos en el mes en la cuenta (Exceeds the limit of allowed deposits in a month of the account)",
                "origin_id": "fad55396_2044_e5_14015eb1e2cc",
                "fecha_operacion": "2025010",
                "beneficiary_bank_code": "9072",
                "clave_de_rastreo": CLAVE_RASTREO,
                "huella_digital": "7b087398e2bbc4d0745044ecb322d52dffb2e84650c4c71bd79fa61458",
                "concepto": "fad55396-2044-4850-96e5-14015eb1e2cc",
                "beneficiary_name": "Elena",
                "beneficiary_clabe": "79000134141517",
                "numeric_ref": "1503653",
                "cep_link": "https://www.banxico.org.mx/cep/go?i=90710&s=20220921&d=Z",
            },
            "legal_operation_entity": {
                "name": "Nvio",
                "country_code_iso_2": "MX",
                "image_id": "nvio",
            },
        }
    ],
}

BITSO_SPEI_INIT_WITHDRAWAL_PENDING_RESPONSE = {
    "success": True,
    "payload": {
        "wid": FOREIGN_ID2,
        "status": "pending",
        "created_at": "2023-03-07T19:47:33+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "usdc_trf",
        "method_name": "Circle Transfer",
        "amount": AMOUNT_FOREIGN,
        "asset": CURRENCY_FOREIGN.lower(),
        "protocol": "clabe",
        "integration": "circle-api",
        "details": {
            "origin_id": "6ffbb40c5900c3ddd99dffff",
            "transactionHash": "2FVarUCJvJS21AAL8uqvSBAUrkJQfNZcYjC4V37yCydtCPDeunUavAKSFPLDrqtoKRRodLNjU9JMCXnDKiZag3Fd",
            "address": "*****ksqQcKF7KcDNnNuSmiQmdq7k9CG************",
            "addressTag": None,
            "chain": "SOL",
        },
    },
}

BITSO_SPEI_WITHDRAWAL_SUCCESS_CALLBACK = {
    "event": "withdrawal",
    "payload": {
        "wid": FOREIGN_ID,
        "status": "complete",
        "created_at": "2017-07-09T19:22:38+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "rp",
        "method_name": "Ripple",
        "amount": "57",
        "asset": CURRENCY_FOREIGN.lower(),
        "network": "rp",
        "protocol": "clabe",
        "integration": "rippled",
        "details": {
            "address": "*******LK5R5Am25ArfXFmqg**********",
            "destination_tag": "64136557",
            "ripple_transaction_hash": "33EA42FC7A06F062A7B843AF4DC7C0AB00D6644DFDF4C5D354A87C035813D321",
            "clave_de_rastreo": CLAVE_RASTREO,
        },
    },
}

BITSO_SPEI_FAIL_WITHDRAWAL_COMPENSATION_RESPONSE: dict[str, ty.Any] = {
    "payload": [
        {
            "amount": "3134.41",
            "asset": "mxn",
            "created_at": "2025-04-07T21:31:11+00:00",
            "currency": "mxn",
            "details": {
                "cep_link": "",
                "clave": 9312595,
                "clave_rastreo": CLAVE_RASTREO,
                "concepto": "Excede el l\u00edmite de abonos permitidos en el mes en la cuenta (Exceeds the limit of allowed deposits in a month of the account)",
                "deposit_type": "FAIL_WITHDRAWAL_COMPENSATION",
                "numeric_reference": "",
                "receive_clabe": "",
                "sender_bank": 90728,
                "sender_clabe": "",
                "sender_name": "",
                "sender_rfc_curp": "",
            },
            "fid": FOREIGN_ID2,
            "integration": "praxis",
            "legal_operation_entity": {
                "country_code_iso_2": "MX",
                "image_id": "nvio",
                "name": "<hidden>",
            },
            "method": "praxis",
            "method_name": "SPEI Transfer",
            "network": "spei",
            "protocol": "clabe",
            "status": "complete",
        }
    ],
    "success": True,
}

# Дополнительные колбэки для тестов
BITSO_SPEI_DEPOSIT_PENDING_CALLBACK = {
    "event": "funding",
    "payload": {
        "fid": FOREIGN_ID,
        "deposit_id": "dep",
        "status": "pending",
        "created_at": "2024-12-25T14:04:46+00:00",
        "updated_at": "2024-12-25T14:06:46+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "amount": str(AMOUNT_FOREIGN),
        "asset": CURRENCY_FOREIGN.lower(),
        "sender_clabe": SENDER_CLABE,
        "receiver_clabe": CLABE1,
        "details": {
            "sender_name": "MARIO PIu00a5A",
            "sender_clabe": SENDER_CLABE,
            "receive_clabe": CLABE1,
            "sender_bank": "40012",
            "clave": "7702553",
            "clave_rastreo": CLAVE_RASTREO,
            "numeric_reference": "1712240",
            "concepto": "test 2512",
            "sender_rfc_curp": "DUPM920620C22",
        },
    },
}

BITSO_SPEI_DEPOSIT_PROCESSING_CALLBACK = {
    "event": "funding",
    "payload": {
        "fid": FOREIGN_ID,
        "deposit_id": "dep",
        "status": "processing",
        "created_at": "2024-12-25T14:04:46+00:00",
        "updated_at": "2024-12-25T14:06:46+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "amount": str(AMOUNT_FOREIGN),
        "asset": CURRENCY_FOREIGN.lower(),
        "sender_clabe": SENDER_CLABE,
        "receiver_clabe": CLABE1,
        "details": {
            "sender_name": "MARIO PIu00a5A",
            "sender_clabe": SENDER_CLABE,
            "receive_clabe": CLABE1,
            "sender_bank": "40012",
            "clave": "7702553",
            "clave_rastreo": CLAVE_RASTREO,
            "numeric_reference": "1712240",
            "concepto": "test 2512",
            "sender_rfc_curp": "DUPM920620C22",
        },
    },
}

BITSO_SPEI_DEPOSIT_FAILED_CALLBACK = {
    "event": "funding",
    "payload": {
        "fid": FOREIGN_ID,
        "deposit_id": "dep",
        "status": "failed",
        "created_at": "2024-12-25T14:04:46+00:00",
        "updated_at": "2024-12-25T14:06:46+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "amount": str(AMOUNT_FOREIGN),
        "asset": CURRENCY_FOREIGN.lower(),
        "sender_clabe": SENDER_CLABE,
        "receiver_clabe": CLABE1,
        "details": {
            "sender_name": "MARIO PIu00a5A",
            "sender_clabe": SENDER_CLABE,
            "receive_clabe": CLABE1,
            "sender_bank": "40012",
            "clave": "7702553",
            "clave_rastreo": CLAVE_RASTREO,
            "numeric_reference": "1712240",
            "concepto": "test 2512",
            "sender_rfc_curp": "DUPM920620C22",
        },
    },
}

BITSO_SPEI_DEPOSIT_GET_STATUS_PENDING_RESPONSE = {
    "success": True,
    "payload": [
        {
            "fid": FOREIGN_ID,
            "status": "pending",
            "created_at": "2024-12-25T14:04:46+00:00",
            "updated_at": "2024-12-25T14:06:46+00:00",
            "currency": CURRENCY_FOREIGN.lower(),
            "amount": str(AMOUNT_FOREIGN),
            "asset": CURRENCY_FOREIGN.lower(),
            "sender_clabe": SENDER_CLABE,
            "receiver_clabe": CLABE1,
            "details": {
                "sender_name": "MARIO PIu00a5A",
                "sender_clabe": SENDER_CLABE,
                "receive_clabe": CLABE1,
                "sender_bank": "40012",
                "clave": "7702553",
                "clave_rastreo": CLAVE_RASTREO,
                "numeric_reference": "1712240",
                "concepto": "test 2512",
                "sender_rfc_curp": "DUPM920620C22",
            },
        }
    ],
}

BITSO_SPEI_DEPOSIT_GET_STATUS_PROCESSING_RESPONSE = {
    "success": True,
    "payload": [
        {
            "fid": FOREIGN_ID,
            "status": "processing",
            "created_at": "2024-12-25T14:04:46+00:00",
            "updated_at": "2024-12-25T14:06:46+00:00",
            "currency": CURRENCY_FOREIGN.lower(),
            "amount": str(AMOUNT_FOREIGN),
            "asset": CURRENCY_FOREIGN.lower(),
            "sender_clabe": SENDER_CLABE,
            "receiver_clabe": CLABE1,
            "details": {
                "sender_name": "MARIO PIu00a5A",
                "sender_clabe": SENDER_CLABE,
                "receive_clabe": CLABE1,
                "sender_bank": "40012",
                "clave": "7702553",
                "clave_rastreo": CLAVE_RASTREO,
                "numeric_reference": "1712240",
                "concepto": "test 2512",
                "sender_rfc_curp": "DUPM920620C22",
            },
        }
    ],
}

BITSO_SPEI_WITHDRAWAL_PROCESSING_CALLBACK = {
    "event": "withdrawal",
    "payload": {
        "wid": FOREIGN_ID,
        "status": "processing",
        "created_at": "2025-08-01T15:19:04+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "praxis",
        "method_name": "SPEI Transfer",
        "amount": str(AMOUNT_FOREIGN),
        "asset": CURRENCY_FOREIGN.lower(),
        "network": "spei",
        "protocol": "clabe",
        "integration": "praxis",
        "details": {
            "origin_id": "20433c61_6a23_4baf_9a89_de20a9061761",
            "fecha_operacion": "",
            "beneficiary_bank_code": "",
            "huella_digital": "",
            "concepto": "20433c61-6a23-423f_9a89_de20a5061760",
            "beneficiary_name": "Alexis Dqenas Gonzalvez",
            "beneficiary_clabe": "058597055078586891",
            "numeric_ref": "3117004",
            "cep_link": None,
        },
    },
}

BITSO_SPEI_WITHDRAWAL_FAILED_CALLBACK = {
    "event": "withdrawal",
    "payload": {
        "wid": FOREIGN_ID,
        "status": "failed",
        "created_at": "2025-08-01T15:19:04+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "praxis",
        "method_name": "SPEI Transfer",
        "amount": str(AMOUNT_FOREIGN),
        "asset": CURRENCY_FOREIGN.lower(),
        "network": "spei",
        "protocol": "clabe",
        "integration": "praxis",
        "details": {
            "origin_id": "20433c61_6a23_4baf_9a89_de20a9061761",
            "fecha_operacion": "20250801",
            "beneficiary_bank_code": "40058",
            "clave_de_rastreo": CLAVE_RASTREO,
            "huella_digital": "0a3a94d79072ff1667372055b3702b373b34c3abacd756afba6e94893898502a",
            "concepto": "20433c61-6a23-423f_9a89_de20a5061760",
            "beneficiary_name": "Alexis Dqenas Gonzalvez",
            "beneficiary_clabe": "058597055078586891",
            "numeric_ref": "3117004",
            "cep_link": None,
            "fail_reason": "Cuenta bloqueada (Blocked Account)",
        },
    },
}

BITSO_SPEI_WITHDRAWAL_SUCCESS_CALLBACK_1 = {
    "event": "withdrawal",
    "payload": {
        "wid": FOREIGN_ID,
        "status": "complete",
        "created_at": "2025-08-01T15:19:04+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "praxis",
        "method_name": "SPEI Transfer",
        "amount": str(AMOUNT_FOREIGN),
        "asset": CURRENCY_FOREIGN.lower(),
        "network": "spei",
        "protocol": "clabe",
        "integration": "praxis",
        "details": {
            "origin_id": "20433c61_6a23_4baf_9a89_de20a9061761",
            "fecha_operacion": "20250801",
            "beneficiary_bank_code": "40058",
            "clave_de_rastreo": CLAVE_RASTREO,
            "huella_digital": "0a3a94d79072ff1667372055b3702b373b34c3abacd756afba6e94893898502a",
            "concepto": "20433c61-6a23-423f_9a89_de20a5061760",
            "beneficiary_name": "Alexis Dqenas Gonzalvez",
            "beneficiary_clabe": "058597055078586891",
            "numeric_ref": "3117004",
            "cep_link": "https://www.banxico.org.mx/cep/go?i=90710&s=20220921&d=FfclqYSy5RGZqFD4",
        },
    },
}

BITSO_SPEI_WITHDRAWAL_SUCCESS_CALLBACK_2 = {
    "event": "withdrawal",
    "payload": {
        "wid": FOREIGN_ID,
        "status": "complete",
        "created_at": "2017-07-09T19:22:38+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "rp",
        "method_name": "Ripple",
        "amount": str(AMOUNT_FOREIGN),
        "asset": CURRENCY_FOREIGN.lower(),
        "network": "rp",
        "protocol": "clabe",
        "integration": "rippled",
        "details": {
            "address": "*******LK5R5Am25ArfXFmqg**********",
            "destination_tag": "64136557",
            "ripple_transaction_hash": "33EA42FC7A06F062A7B843AF4DC7C0AB00D6644DFDF4C5D354A87C035813D321",
            "clave_de_rastreo": CLAVE_RASTREO,
        },
    },
}

BITSO_SPEI_WITHDRAWAL_REFUND_SUCCESS_CALLBACK = {
    "event": "funding",
    "payload": {
        "fid": FOREIGN_ID,
        "deposit_id": "???",
        "status": "complete",
        "created_at": "2024-12-25T14:04:46+00:00",
        "updated_at": "2025-02-25T10:05:00+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "praxis",
        "method_name": "SPEI Transfer",
        "amount": str(AMOUNT_FOREIGN),
        "asset": CURRENCY_FOREIGN.lower(),
        "network": "spei",
        "protocol": "clabe",
        "integration": "praxis",
        "sender_clabe": SENDER_CLABE,
        "receiver_clabe": CLABE1,
        "details": {
            "sender_name": "MARIO PIu00a5A",
            "sender_clabe": SENDER_CLABE,
            "receive_clabe": None,
            "sender_bank": "40012",
            "clave": "7702553",
            "clave_rastreo": CLAVE_RASTREO,
            "clave_rastreo_origen": CLAVE_RASTREO,
            "numeric_reference": "1712240",
            "concepto": "test 2512",
            "cep_link": "",
            "sender_rfc_curp": "DUPM920620C22",
            "deposit_type": "FAIL_WITHDRAWAL_COMPENSATION",
        },
    },
}

BITSO_SPEI_FAIL_WITHDRAWAL_COMPENSATION_CALLBACK = {
    "event": "funding",
    "payload": {
        "fid": FOREIGN_ID,
        "deposit_id": "???",
        "status": "complete",
        "created_at": "2025-09-27T14:04:05+00:00",
        "currency": CURRENCY_FOREIGN.lower(),
        "method": "praxis",
        "method_name": "SPEI Transfer",
        "amount": str(AMOUNT_FOREIGN),
        "asset": CURRENCY_FOREIGN.lower(),
        "network": "spei",
        "protocol": "clabe",
        "integration": "praxis",
        "sender_clabe": SENDER_CLABE,
        "receiver_clabe": CLABE1,
        "details": {
            "sender_name": "MARIO PIÑA",
            "sender_clabe": SENDER_CLABE,
            "receive_clabe": "710969000019152655",
            "sender_bank": "40012",
            "clave": "17450736",
            "clave_rastreo": CLAVE_RASTREO,
            "concepto": "Cuenta cancelada (Cancelled Account)",
            "deposit_type": "FAIL_WITHDRAWAL_COMPENSATION",
            "clave_rastreo_origen": CLAVE_RASTREO,
            "origin_wid": FOREIGN_ID2,
            "origin_client_id": "47db6473_974a_4ba9_a197_d642312591ce",
            "operation_date": "2025-09-29",
        },
    },
}
