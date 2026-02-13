from datetime import timedelta

from rozert_pay.common import const

WITHDRAW_STATUS_MATCHING = {
    "Pending": const.TransactionStatus.PENDING,
    "In Progress": const.TransactionStatus.PENDING,
    "Partially Approved": const.TransactionStatus.SUCCESS,
    "Approved": const.TransactionStatus.SUCCESS,
    "Canceled": const.TransactionStatus.FAILED,
    "Declined": const.TransactionStatus.FAILED,
    "Error": const.TransactionStatus.FAILED,
}

DEPOSIT_ERROR_API_STATUS = "ERROR"
DEPOSIT_SUCCESS_GW_STATUS = "APPROVED"
DEPOSIT_ERROR_GW_STATUSES = ["DECLINED", "ERROR"]

TRX_EXTRA_FIELD_INIT_TRANSACTION_ID = "initForeignTransactionId"
TRX_EXTRA_FIELD_SESSION_TOKEN = "sessionToken"
TRX_EXTRA_FIELD_THREEDS_PAYMENT_RELATED_TRANSACTION_ID = (
    "threedsPaymentRelatedTransactionId"
)
TRX_EXTRA_FIELD_THREEDS_AFTER_REDIRECT_REQUEST_DONE = (
    "isThreedsAfterRedirectRequestDone"
)
TRX_EXTRA_FIELD_THREEDS_TRANSACTION_IDS = "threedsTransactionIds"
TRX_EXTRA_FIELD_PAYOUT_REQUEST_ID = "payoutRequestId"

PAYMENT_NOT_PERFORMED_PENDING_WINDOW = timedelta(minutes=15)
