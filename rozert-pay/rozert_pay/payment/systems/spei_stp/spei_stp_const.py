from decimal import Decimal

from rozert_pay.payment import entities

ORDER_STATUS_CANCEL = "Cancel"
ORDER_STATUS_SUCCESS = "Success"
ORDER_STATUS_REFUND = "Refund"
COMPANY_NAME_EMPRESA = "UNOCAPALI LA PAZ OPERADORA SA DE CV"
PAYOUT_EMPRESA = "BETMASTER_MX"
ESTADO_SUCCESS = 0
ESTADO_NO_TRANSACTIONS_FOR_DATE = 6
STATUS_MAP = {
    "LQ": entities.TransactionStatus.SUCCESS,
    "TLQ": entities.TransactionStatus.SUCCESS,
    "CCO": entities.TransactionStatus.SUCCESS,
    "CCR": entities.TransactionStatus.SUCCESS,
    "D": entities.TransactionStatus.FAILED,
    "TCL": entities.TransactionStatus.FAILED,
    "RL": entities.TransactionStatus.FAILED,
    "RA": entities.TransactionStatus.FAILED,
    "CXO": entities.TransactionStatus.PENDING,
    # https://betmaster.slack.com/archives/C05HE26E2SY/p1723191153105919?thread_ts=1723143031.753889&cid=C05HE26E2SY
    "A": entities.TransactionStatus.PENDING,
    "CL": entities.TransactionStatus.FAILED,
    # https://betmaster.slack.com/archives/C05HE26E2SY/p1723492261489809?thread_ts=1723143031.753889&cid=C05HE26E2SY
    "L": entities.TransactionStatus.PENDING,
    "E": entities.TransactionStatus.PENDING,
    "EA": entities.TransactionStatus.PENDING,
    "CCE": entities.TransactionStatus.FAILED,
    "RE": entities.TransactionStatus.FAILED,
    "TA": entities.TransactionStatus.PENDING,
    "C": entities.TransactionStatus.PENDING,
    "CN": entities.TransactionStatus.PENDING,
    "EC": entities.TransactionStatus.PENDING,
    "XD": entities.TransactionStatus.PENDING,
    "RB": entities.TransactionStatus.FAILED,
}
MAX_CLABE = 100000
MIN_NON_REJECTED_DEPOSIT_AMOUNT_MXN = Decimal(3)
