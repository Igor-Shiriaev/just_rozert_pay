BITSO_SPEI_STATUS_SUCCESS = "complete"
DECLINE_REASON_FAILED = "failed"

DECLINE_CODES = [
    "1003",
    "1101",
    "0402",
    "0404",
    "0410",
    "0343",
    "0303",
    "500",
    "0101",
    "0111",
    "0702",
    "0303",
    "0304",
    "0602",
    "0714",
    "0501",
    "Clave de institución ordenante no catalogada (The code of the ordering institution is unknown)",
    "Cuenta bloqueada (Blocked Account)",
    "Cuenta cancelada (Cancelled Account)",
    "Cuenta inexistente (Non-Existing Account)",
    "Cuenta no pertenece al participante emisor (The account does not belong to the sending party)",
    "Excede el límite de abonos permitidos en el mes en la cuenta (It exceeds the account's monthly limit of allowed deposits)",
    "Excede el límite de saldo autorizado en la cuenta (It exceeds the account's authorized balance limit)",
    "Falta información mandatoria para completar el pago (It misses mandatory information to complete the payment)",
    "Not mapped error	Yes",
    "Tipo de cuenta no corresponde (The account type does not match)",
    "Tipo de operación errónea (Erroneous operation type)",
    "Tipo de pago erróneo (Erroneous payment type)",
    DECLINE_REASON_FAILED,
]

BITSO_SPEI_IS_PAYOUT_REFUNDED = "bitso_spei_is_payout_refunded"
BITSO_SPEI_PAYOUT_REFUND_DATA = "bitso_spei_payout_refund_data"

# https://docs.bitso.com/bitso-payouts-funding/docs/filter-your-mxn-withdrawal-search
# You can use this parameter to track a specific withdrawal using its clave_de_rastreo
# value. However, it is especially helpful when searching for a specific refund deposit.
#
# Using the tracking key (clave_de_rastreo) returned by the webhook for the
# completed withdrawal, which eventually becomes a reversed withdrawal, you can
# search for a specific refund deposit.
BITSO_CLAVE_RASTREO_FIELD = "claveRastreo"
