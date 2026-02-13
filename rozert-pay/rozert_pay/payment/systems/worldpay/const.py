from enum import StrEnum

from rozert_pay.common.const import TransactionExtraFields


class WorldpayPayloadType(StrEnum):
    CREATE_ORDER = "create_order"
    GET_STATUS = "get_status"
    CALLBACK = "callback"


NOT_READY_ERROR_MESSAGES = frozenset(
    {
        "Order not ready",
        "Could not find payment for order",
    },
)

WORLDPAY_COOKIES_KEY = "worldpay_cookies"
TIMEOUT_SECONDS = 60


class WorldpayTransactionExtraFields(TransactionExtraFields):
    SESSION_ID = "session_id"
    REQUEST_3DS_CHALLENGE = "request_3ds_challenge"
