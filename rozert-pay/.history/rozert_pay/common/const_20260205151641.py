from pathlib import Path

from django.db.models import TextChoices


class TransactionType(TextChoices):
    DEPOSIT = "deposit", "Deposit"
    WITHDRAWAL = "withdrawal", "Withdrawal"


class TransactionStatus(TextChoices):
    PENDING = "pending", "Pending"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"

    # Refunded by us
    REFUNDED = "refunded", "Refunded"

    # Chargeback by client
    # When a chargeback is received -> the same as change deposit success -> failed state
    CHARGED_BACK = "charged_back", "Charged Back"

    # When a chargeback is reversed -> the same as return deposit to success state.
    CHARGED_BACK_REVERSAL = "charged_back_reversal", "Charged Back Reversal"


class TransactionDeclineCodes(TextChoices):
    USER_HAS_NOT_FINISHED_FLOW = (
        "USER_HAS_NOT_FINISHED_FLOW",
        "User has not finished flow",
    )
    INTERNAL_ERROR = "INTERNAL_ERROR", "Internal error"
    DEPOSIT_NOT_PROCESSED_IN_TIME = (
        "DEPOSIT_NOT_PROCESSED_IN_TIME",
        "Deposit not processed in time",
    )
    NO_OPERATION_PERFORMED = "NO_OPERATION_PERFORMED", "No operation performed"
    TRANSACTION_NOT_FOUND = "TRANSACTION_NOT_FOUND", "Transaction not found"

    # For our system declines, when we 100% sure no payout requests was sent
    SYSTEM_DECLINE = "system_decline", "System decline"

    # Decline because of limits
    LIMITS_DECLINE = "LIMITS_DECLINE", "Limits decline"

    # Risk lists decline
    RISK_DECLINE = "risk_decline", "Risk decline"


class EventType(TextChoices):
    ERROR = "error", "Error"
    CALLBACK_SENDING_ATTEMPT = "callback_sending_attempt", "Callback Sending Attempt"
    EXTERNAL_API_REQUEST = "external_api_request", "External API Request"
    CALLBACK_RETRY_REQUESTED = "callback_retry_requested", "Callback Retry Requested"

    IMPORTANT = "important", "!!! Important !!!"

    TRANSACTION_ACTUALIZATION = (
        "transaction_actualization",
        "Transaction Actualization (Admin)",
    )
    TRANSACTION_SET_STATUS = "transaction_set_status", "Transaction Set Status (Admin)"
    WITHDRAWAL_STUCK_IN_PROCESSING = (
        "withdrawal_stuck_in_processing",
        "Withdrawal Stuck in Processing",
    )

    INFO = "info", "Info"
    CUSTOMER_REDIRECT_RECEIVED = (
        "customer_redirect_received",
        "Customer Redirect Received",
    )
    CHARGE_BACK = "charge_back", "Charge Back"
    CHARGE_BACK_REVERSAL = ("charge_back_reversal", "Charge Back Reversal")
    CREATE_DEPOSIT_INSTRUCTION = (
        "create_deposit_instruction",
        "Create Deposit Instruction",
    )
    PAYOUT_REFUND = "payout_refund", "Payout Refund"
    REVERT_TO_INITIAL = "revert_to_initial", "Revert to Initial Status"

    DECLINED_BY_LIMIT = "declined_by_limit", "Declined by Limit"
    DEBUG = "debug", "Debug messages"

    DECLINED_BY_RISK_LIST = "declined_by_risk_list", "Declined by Risk List"
    AUDIT_ITEM_RECEIVED = "audit_item_received", "Received audit item"


class CallbackType(TextChoices):
    DEPOSIT_ACCOUNT_CREATED = "deposit_account_created", "Deposit Account Created"
    DEPOSIT_RECEIVED = "deposit_received", "Deposit Received"
    TRANSACTION_UPDATED = "transaction_updated", "Transaction Updated"


class CallbackStatus(TextChoices):
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"
    PENDING = "pending", "Pending"


CARDPAY_APPLEPAY_BANKCARD_FLAG = "cardpay_applepay_bankcard_payment_method"
CARDPAY_APPLEPAY_BANKCARD_SWITCH = "cardpay_applepay_bankcard_payment_switch"


class ACLLevel(TextChoices):
    READ = "read", "Read"
    WRITE = "write", "Write"


class PaymentSystemType(TextChoices):
    STP_SPEI = "spei_stp", "SPEI STP"
    STP_CODI = "stp_codi", "STP CODI"
    D24_MERCADOPAGO = "d24_mercadopago", "D24 MercadoPago"
    PAYCASH = "paycash", "PayCash"
    PAYPAL = "paypal", "PayPal"
    BITSO_SPEI = "bitso_spei", "Bitso SPEI"
    MUWE_SPEI = "muwe_spei", "MUWE SPEI"
    APPEX = "appex", "Appex"
    ILIXIUM = "ilixium", "Ilixium"
    WORLDPAY = "worldpay", "Worldpay"

    CONEKTA_OXXO = "conekta_oxxo", "Conekta OXXO"
    CARDPAY_CARDS = "cardpay_cards", "Cardpay Cards"
    CARDPAY_APPLEPAY = "cardpay_applepay", "Cardpay Applepay"
    MPESA_MZ = "mpesa_mz", "M-Pesa MZ"
    NUVEI = "nuvei", "Nuvei"


class CeleryQueue(TextChoices):
    HIGH_PRIORITY = "high", "High"
    NORMAL_PRIORITY = "normal", "Normal"
    LOW_PRIORITY = "low", "Low"

    # For service, cleanup tasks
    SERVICE = "service", "Service"


class InstructionType(TextChoices):
    INSTRUCTION_FILE = "instruction_file", "Instruction File"
    INSTRUCTION_QR_CODE = "instruction_qr_code", "Instruction QR Code"
    INSTRUCTION_DEPOSIT_ACCOUNT = (
        "instruction_deposit_account",
        "Instruction Deposit Account",
    )
    INSTRUCTION_REFERENCE = "instruction_reference", "Instruction Reference"


class IncomingCallbackError(TextChoices):
    IP_NOT_WHITELISTED = "ip_not_whitelisted", "IP not whitelisted"
    INVALID_SIGNATURE = "invalid_signature", "Invalid signature"
    PARSING_ERROR = "parsing_error", "Parsing error"
    VALIDATION_ERROR = "validation_error", "Validation error"
    UNKNOWN_ERROR = "unknown_error", "Unknown error"
    AUTHORIZATION_ERROR = "authorization_error", "Authorization error"


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


PAYMENT_SYSTEMS_WITH_WITHDRAWALS: list[PaymentSystemType] = [
    PaymentSystemType.PAYPAL,
    PaymentSystemType.NUVEI,
]


class TransactionExtraFields:
    IS_FINALIZATION_PERFORMED = "is_finalization_performed"
    IS_CHARGEBACK_RECEIVED = "is_chargeback_received"
    IS_REFUND_RECEIVED = "is_refund_received"
    IS_CHARGEBACK_REVERSAL_RECEIVED = "is_chargeback_reversal_received"

    REFUNDED_AMOUNT = "refunded_amount"

    BYPASS_AMOUNT_VALIDATION_FOR = "bypass_amount_validation_for"

    # Periodic status check fields
    COUNT_STATUS_CHECKS_SCHEDULED = "count_status_checks_scheduled"
    LAST_STATUS_CHECK_SCHEDULE = "last_status_check_schedule"

    # Data received in redirect request. I.e. PaRes for 3DS
    REDIRECT_RECEIVED_DATA = "redirect_received_data"

    # Risk lists


CARD_EXPIRATION_REGEXP = r"^(0[1-9]|1[0-2])/(\d{2}|\d{4})$"

BACK_SECRET_KEY_HEADER = "X-Back-Secret-Key"
