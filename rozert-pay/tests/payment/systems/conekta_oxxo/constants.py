from typing import Any

SUCCESS_CREATE_DEPOSIT = {
    "id": "123",
    "livemode": False,
    "created_at": 1656547671,
    "currency": "MXN",
    "charges": {
        "data": [
            {
                "payment_method": {
                    "service_name": "OxxoPay",
                    "barcode_url": "https://s3.amazonaws.com/cash_payment_barcodes/sandbox_reference.png",
                    "object": "cash_payment",
                    "type": "oxxo",
                    "expires_at": 1656634070,
                    "store_name": "OXXO",
                    "reference": "50 cent",
                },
            },
        ],
    },
    "object": "success",
    "description": "Payment from order",
    "status": "paid",
    "amount": 13500,
    "paid_at": 1656547702,
    "fee": 537,
    "customer_id": None,
    "order_id": "ord_2s53K99C8GXVmCfPm",
}

PENDING_CREATE_DEPOSIT = {
    "object": "order",
    "id": "123",
    "amount": 3001.00,
    "currency": "MXN",
    "payment_status": "pending_payment",
}

TRANSACTION_STATUS_NOT_FOUND = {
    "object": "error",
    "type": "resource_not_found_error",
    "message": "The resource you requested could not be found.",
    "code": "resource_not_found_error",
    "details": [
        {
            "param": "id",
            "message": "The resource you requested could not be found.",
        }
    ],
}

DECLINE_CREATE_DEPOSIT = {
    "object": "error",
    "type": "parameter_validation_error",
    "message": "The parameter amount is invalid.",
    "code": "parameter_validation_error",
    "details": [
        {
            "param": "amount",
            "message": "The parameter amount is invalid.",
        },
    ],
}


SUCCESS_GET_DEPOSIT_STATUS = {
    "object": "success",
    "id": "123",
    "amount": 3001.00,
    "currency": "MXN",
    "payment_status": "paid",
}


USER_DATA = {
    "phone": "+1234567890",
    "email": "test@test.com",
    "first_name": "John",
    "last_name": "Doe",
}


WEBHOOK_KEYS_MOCK_BODY: dict[str, Any] = {
    "next_page_url": None,
    "previous_page_url": None,
    "has_more": False,
    "object": "list",
    "data": [
        {
            "active": True,
            "livemode": False,
            "created_at": 1749717681,
            "deactivated_at": None,
            "deleted": None,
            "id": "684a92b194a1c60019317ab8",
            "object": "webhook_key",
            "public_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1gwrl3M9HDfPdbH4chZ1\n1Ipn0OpF9fGV27cBK0bdW2dIg7sS24ZpLc4ay1HbHQWMlOl/azDugzalqWWlvSIK\n0KAReGOaYtd8oG7nApc+180MkkJsFwDoFmyaxWGLjB4P19NO0S5fXW19rCVYD+rg\nxRjlbC+Ll514b5NJa+6skXAAZnKrqCrqY1XAkLhiu6bx5zHt5U7gSUGgnrlD0M1E\no3A1pd4rJoBtU4UILhnywjUTQS8u8t3HzrCO29CA1h5nXLw3qj+REHB2ZfYoWb7c\nq1vmE2vG4NRFsMeoU/fJfenUM2Xedo0WJHLEJS9w7X3bV7Ni9i7N4QvsTPtEiH0y\nCwIDAQAB\n-----END PUBLIC KEY-----\n",
        },
        {
            "active": False,
            "livemode": False,
            "created_at": 1749717610,
            "deactivated_at": 1749717681,
            "deleted": None,
            "id": "684a926a94a1c6001931793e",
            "object": "webhook_key",
            "public_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmoKzKwi/YVdEgbWh0j6x\n7El9M/2NYkQhZImCRa/iu/HFJ60RDqLS+c98DUVMD79BFIBJOy+7ti1n4dQt0N8x\n4vvhFzoN88Yhc2I/Jdc2H7gyZv5ue3Laq/qpFBE7yBWAYIkUi1Wf4tZ7k6FOSc+W\nmUqYpUgCSo63sIVvf/uP4B4kd+x8Dfm5PdZSuF/blSNud/AojYxufC1P0zqdeMfF\n4SqKdV2bO301aYQlKmAIRSikgM/J9UuScXjPKNx2h0DQOsdzo2O4AaJGfG3+2FdC\nErirqcnFibQyocbYuErxirYj4Aq3OcQFqCFZLWZq1156sprd5SOaIIeLHS1tmBCu\nawIDAQAB\n-----END PUBLIC KEY-----\n",
        },
        {
            "active": None,
            "livemode": False,
            "created_at": 1749717273,
            "deactivated_at": 1749717610,
            "deleted": None,
            "id": "684a9119068099001b21f7e0",
            "object": "webhook_key",
            "public_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAp2M/PoMOoaa6Yk562jES\ntlBWdganozzEcastPHTDZShu4EpupuBQDiFXSImM9gnLEkETMwxHnbH1nqSgD3mg\n+qnUW6baJGTYmTwlD+DgLtOLFFk4YBS8LKsosD/pbeG/1KVV+JwwvCpSqF5xj8fI\niDVsbXD433e75E0XDXToTQLoJMtWaw2SKwurRHuhmviDBRHFA6K53PO81K3/xp01\nSi77Kn2swm50nUzazyqpTlMAWqoLlkO72ekJFQSTZP5zBpFWaTOji4rGf5H1vlIE\n3yYFPtSEfx+llhKLvzwJVL6InApOk1DtxnpeAnFuBFPAHKFxmYNyWSrIlcXDaHf5\nbQIDAQAB\n-----END PUBLIC KEY-----\n",
        },
    ],
}


IGNORING_CALLBACK_MOCK_BODY: dict[str, Any] = {
    "data": {
        "object": {
            "id": "68499f7d94a1c60017ab958e",
            "livemode": True,
            "created_at": 1749655421,
            "currency": "MXN",
            "payment_method": {
                "service_name": "OxxoPay",
                "barcode_url": "https://barcodes.digitalfemsa.io/6452aa98d4def4a91572e484ab6d83fcdac315d1.png",
                "store": "10OBR50S5Q",
                "auth_code": 96767928,
                "object": "cash_payment",
                "type": "oxxo",
                "expires_at": 1749741820,
                "store_name": "OXXO",
                "reference": "93006527613140",
                "cashier_id": "NOUSUARIO",
            },
            "object": "charge",
            "description": "Payment from order",
            "device_fingerprint": "",
            "status": "paid",
            "amount": 40000,
            "paid_at": 1749656266,
            "fee": 1810,
            "customer_id": "",
            "order_id": "123",
        },
        "previous_attributes": {},
    },
    "livemode": True,
    "webhook_status": "pending",
    "webhook_logs": [
        {
            "id": "webhl_2y9LwtJMtmb3fbFZu",
            "url": "https://ps.rozert.cloud/api/ps/conekta-oxxo/",
            "failed_attempts": 0,
            "last_http_response_status": -1,
            "response_data": None,
            "object": "webhook_log",
            "last_attempted_at": 0,
        }
    ],
    "id": "6849a2ccfd01bf000120dadc",
    "object": "event",
    "type": "charge.paid",
    "created_at": 1749656269,
}
