from typing import Union


DEPOSIT_REQUEST_PAYLOAD: dict[str, Union[str, dict[str, str]]] = {
    "amount": "2333.71",
    "currency": "MXN",
    "wallet_id": "",
    "customer_id": "customer1",
    "user_data": {
        "country": "MX",
        "email": "test@test.com",
        "first_name": "John",
        "last_name": "Doe",
        "phone": "+1234567890",
    },
    "mexican_curp": "",
    "redirect_url": "https://redirect.url",
}


WITHDRAW_REQUEST_PAYLOAD = {
    "amount": "2333.71",
    "currency": "MXN",
    "wallet_id": "",
    "customer_id": "customer1",
    "user_data": {
        "country": "MX",
        "first_name": "John",
        "last_name": "Doe",
    },
    "mexican_curp": "",
    "withdraw_to_account": "",
}
