from rozert_pay.common import const
from rozert_pay.payment.types import CustomerWalletExtraKey

# MUWE transaction status codes
# Source: MUWE API Documentation
MUWE_STATUS_PENDING = 1  # Transaction is being processed
MUWE_STATUS_SUCCESS = 2  # Transaction completed successfully
MUWE_STATUS_FAILED = 3  # Transaction failed

MUWE_SPEI_IDENTIFIER = "identifier"
MUWE_SPEI_MCH_ORDER_NO = "mchOrderNo"

# Map MUWE status codes to internal TransactionStatus
STATUS_MAP = {
    MUWE_STATUS_PENDING: const.TransactionStatus.PENDING,
    MUWE_STATUS_SUCCESS: const.TransactionStatus.SUCCESS,
    MUWE_STATUS_FAILED: const.TransactionStatus.FAILED,
}

# ============================================================================
# WEBHOOK EVENTS
# ============================================================================

# Webhook event types supported by MUWE
EVENT_ORDER_SUCCESS = "order.success"  # Successful deposit/withdrawal
EVENT_NOTIFY_PING = "notify.ping"  # Test webhook (always auto-added)
EVENT_PAYIN_REFUNDED_PARTIAL = "payin.refunded_partial"  # Partial refund
EVENT_PAYIN_REFUNDED = "payin.refunded"  # Full refund
EVENT_SPEI_CHANNEL_STATUS_CHANGED = (
    "spei_channel.status_changed"  # Channel status change
)
EVENT_NOTIFY_CREATED = "notify.created"  # Notification created
EVENT_NOTIFY_UPDATED = "notify.updated"  # Notification updated
EVENT_NOTIFY_DELETED = "notify.deleted"  # Notification deleted

# Default events to subscribe for deposits/withdrawals
DEFAULT_WEBHOOK_EVENTS = [
    EVENT_ORDER_SUCCESS,
    EVENT_NOTIFY_PING,  # Always included by MUWE
]

# ============================================================================
# TRANSACTION EXTRA FIELDS
# ============================================================================

# Extra field keys
EXTRA_REFERENCE = "reference"  # CLABE (18 digits)
EXTRA_ACCOUNT_NO = "accountNo"  # Sender's account number
EXTRA_ACCOUNT_NAME = "accountName"  # Sender's account name
EXTRA_BANK_CODE = "bankCode"  # Sender's bank code
EXTRA_IDENTIFIER = "identifier"  # MUWE transaction identifier
EXTRA_INCOME = "income"  # Amount credited (after fees)
EXTRA_FEE = "fee"  # Transaction fee
EXTRA_SUCCESS_TIME = "successTime"  # Timestamp when transaction succeeded
EXTRA_MCH_ORDER_NO = "mchOrderNo"  # Merchant order number (for withdrawals)

# ============================================================================
# API CONFIGURATION
# ============================================================================

# MUWE API endpoints
API_ENDPOINT_COLLECTION_CREATE = "/api/unified/collection/create"  # Generate CLABE
API_ENDPOINT_PAYOUT_CREATE = "/api/unified/agentpay/apply"  # Create withdrawal
API_ENDPOINT_QUERY_PAYIN = "/common/query/pay_order"  # Query deposit status
API_ENDPOINT_QUERY_PAYOUT = "/common/query/agentpay_order"  # Query withdrawal status

# MUWE webhook management endpoints
API_ENDPOINT_WEBHOOKS_LIST = "/api/v1/webhooks/list"
API_ENDPOINT_WEBHOOKS_CREATE = "/api/v1/webhooks/create"
API_ENDPOINT_WEBHOOKS_UPDATE = "/api/v1/webhooks/update"
API_ENDPOINT_WEBHOOKS_GET = "/api/v1/webhooks/get"
API_ENDPOINT_WEBHOOKS_TEST = "/api/v1/webhooks/test"

# Payment type for SPEI
PAYMENT_TYPE_SPEI = "1"

# Currency
CURRENCY_MXN = "MXN"

# CLABE length
CLABE_LENGTH = 18

# ============================================================================
# ERROR HANDLING
# ============================================================================

# MUWE API response codes
RESPONSE_CODE_SUCCESS = "SUCCESS"
RESPONSE_CODE_FAIL = "FAIL"

# Decline reason for failed transactions
DECLINE_REASON_MUWE_FAILED = "muwe_transaction_failed"
DECLINE_REASON_INVALID_SIGNATURE = "invalid_webhook_signature"
DECLINE_REASON_CLABE_NOT_FOUND = "clabe_not_found"
DECLINE_REASON_API_ERROR = "muwe_api_error"

BANK_CODE_EXTRA_KEY = CustomerWalletExtraKey("bankCode")
ACCOUNT_NAME_EXTRA_KEY = CustomerWalletExtraKey("accountName")
