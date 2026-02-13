from decimal import Decimal
from typing import Any, Union

from currency.utils import to_minor_units
from rozert_pay.payment.entities import CardData
from rozert_pay.payment.systems.worldpay.helpers import generate_worldpay_xml

MERCHANT_CODE = "fake_merchant_code"
ORDER_CODE = "MURADIK"

CARD = {
    "expires": "12/2041",
    "num": "4111111111111111",
    "cvv": "123",
    "holder": "IVAN IVANOV",
}

CARD_DATA = CardData(
    card_num="4111111111111111",  # type: ignore[arg-type]
    card_holder="SALAM 228",
    card_expiration="08/2030",
    card_cvv="123",  # type: ignore[arg-type]
)

BROWSER_DATA = {
    "accept_header": "text/html,application/xhtml+xml",
    "javascript_enabled": True,
    "java_enabled": False,
    "language": "en-US",
    "screen_height": 1080,
    "screen_width": 1920,
    "time_difference": "+3",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "color_depth": 24,
}

SESSION_ID = "test-session-id-12345"

WORLDPAY_DEPOSIT_REQUEST_PAYLOAD: dict[str, Union[str, dict[str, Any]]] = {
    "amount": "2333.71",
    "currency": "MXN",
    "wallet_id": "",
    "customer_id": "customer1",
    "redirect_url": "https://example.com/redirect",
    "user_data": {
        "country": "MX",
        "email": "test@test.com",
        "address": "12345",
        "city": "Mexico City",
        "post_code": "12345",
        "ip_address": "127.0.0.1",
        "phone": "+52 55 1234 5678",
    },
    "card": CARD_DATA.to_dict(),
    "browser_data": BROWSER_DATA,
    "session_id": SESSION_ID,
}


def get_successful_pending_deposit_response(merchant_code: str, order_code: str) -> str:
    successful_deposit_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "SENT_FOR_AUTHORISATION",
                        "AuthorisationId": {"@id": "289567"},
                        "CVCResultCode": {"@description": "NOT CHECKED BY ACQUIRER"},
                        "balance": {
                            "@accountType": "IN_PROCESS_AUTHORISED",
                            "amount": {
                                "@value": str(
                                    int(to_minor_units(Decimal("2333.71"), "MXN"))
                                ),
                                "@currencyCode": "MXN",
                                "@exponent": "2",
                                "@debitCreditIndicator": "credit",
                            },
                        },
                        "cardNumber": "4444********1111",
                        "instalments": "1",
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(successful_deposit_response_payload)


def get_immediate_successful_deposit_response(
    merchant_code: str, order_code: str
) -> str:
    successful_deposit_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "AUTHORISED",
                        "AuthorisationId": {"@id": "289567"},
                        "CVCResultCode": {"@description": "NOT CHECKED BY ACQUIRER"},
                        "balance": {
                            "@accountType": "IN_PROCESS_AUTHORISED",
                            "amount": {
                                "@value": str(
                                    int(to_minor_units(Decimal("2333.71"), "MXN"))
                                ),
                                "@currencyCode": "MXN",
                                "@exponent": "2",
                                "@debitCreditIndicator": "credit",
                            },
                        },
                        "cardNumber": "4444********1111",
                        "instalments": "1",
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(successful_deposit_response_payload)


def get_refused_deposit_response(merchant_code: str, order_code: str) -> str:
    refused_deposit_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "REFUSED",
                        "CVCResultCode": {"@description": "FAILED"},
                        "ISO8583ReturnCode": {
                            "@code": "5",
                            "@description": "REFUSED",
                        },
                        "instalments": 1,
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(refused_deposit_response_payload)


def get_error_deposit_response(merchant_code: str, order_code: str) -> str:
    error_deposit_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "error": {"@code": "7", "#text": "Gateway error"},
                }
            },
        }
    }

    return generate_worldpay_xml(error_deposit_response_payload)


def get_successful_withdraw_response(merchant_code: str, order_code: str) -> str:
    successful_withdraw_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "ok": {
                    "refundReceived": {
                        "@orderCode": order_code,
                        "amount": {
                            "@value": "100",
                            "@currencyCode": "EUR",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                    }
                }
            },
        }
    }

    return generate_worldpay_xml(successful_withdraw_response_payload)


def get_successful_withdraw_callback(merchant_code: str, order_code: str) -> str:
    successful_withdraw_callback_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "notify": {
                "orderStatusEvent": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "amount": {
                            "@value": "1000",
                            "@currencyCode": "EUR",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "SENT_FOR_REFUND",
                        "OCTTxnID": "456231",
                        "balance": {
                            "@accountType": "IN_PROCESS_CAPTURED",
                            "amount": {
                                "@value": "1000",
                                "@currencyCode": "EUR",
                                "@exponent": "2",
                                "@debitCreditIndicator": "debit",
                            },
                        },
                    },
                    "journal": {
                        "@journalType": "SENT_FOR_REFUND",
                        "bookingDate": {
                            "date": {
                                "@dayOfMonth": "30",
                                "@month": "11",
                                "@year": "2020",
                            }
                        },
                        "accountTx": {
                            "@accountType": "IN_PROCESS_CAPTURED",
                            "@batchId": "6",
                            "amount": {
                                "@value": "1000",
                                "@currencyCode": "EUR",
                                "@exponent": "2",
                                "@debitCreditIndicator": "debit",
                            },
                        },
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(successful_withdraw_callback_payload)


def get_refused_withdraw_callback(merchant_code: str, order_code: str) -> str:
    refused_withdraw_callback_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "notify": {
                "orderStatusEvent": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "ECMC-SSL",
                        "amount": {
                            "@value": "310",
                            "@currencyCode": "EUR",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "REFUSED",
                        "ISO8583ReturnCode": {"@code": "5", "@description": "REFUSED"},
                        "OCTTxnID": "345123",
                    },
                    "journal": {
                        "@journalType": "REFUSED",
                        "bookingDate": {
                            "date": {
                                "@dayOfMonth": "30",
                                "@month": "11",
                                "@year": "2020",
                            }
                        },
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(refused_withdraw_callback_payload)


def get_successful_get_status_deposit_response(
    merchant_code: str,
    order_code: str,
) -> str:
    successful_get_deposit_status_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "paymentMethodDetail": {
                            "card": {
                                "@type": "debitcard",
                            }
                        },
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "CAPTURED",
                        "AuthorisationId": {"@id": "289567"},
                        "CVCResultCode": {"@description": "FAILED"},
                        "balance": {
                            "@accountType": "IN_PROCESS_CAPTURED",
                            "amount": {
                                "@value": str(
                                    int(to_minor_units(Decimal("2333.71"), "MXN"))
                                ),
                                "@currencyCode": "MXN",
                                "@exponent": "2",
                                "@debitCreditIndicator": "credit",
                            },
                        },
                        "instalments": "1",
                    },
                    "date": {
                        "@dayOfMonth": "30",
                        "@month": "11",
                        "@year": "2025",
                        "@hour": "12",
                        "@minute": "00",
                        "@second": "00",
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(successful_get_deposit_status_response_payload)


def get_successful_get_status_deposit_response_with_commission_and_net_amounts(
    merchant_code: str,
    order_code: str,
) -> str:
    successful_get_deposit_status_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "paymentMethodDetail": {
                            "card": {
                                "@type": "debitcard",
                            }
                        },
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "SETTLED",
                        "AuthorisationId": {"@id": "289567"},
                        "CVCResultCode": {"@description": "FAILED"},
                        "balance": [
                            {
                                "@accountType": "SETTLED_BIBIT_NET",
                                "amount": {
                                    "@value": str(
                                        int(to_minor_units(Decimal("2033.70"), "MXN"))
                                    ),
                                    "@currencyCode": "MXN",
                                    "@exponent": "2",
                                    "@debitCreditIndicator": "credit",
                                },
                            },
                            {
                                "@accountType": "SETTLED_BIBIT_COMMISSION",
                                "amount": {
                                    "@value": str(
                                        int(to_minor_units(Decimal("300.01"), "MXN"))
                                    ),
                                    "@currencyCode": "MXN",
                                    "@exponent": "2",
                                    "@debitCreditIndicator": "credit",
                                },
                            },
                        ],
                        "instalments": "1",
                    },
                    "date": {
                        "@dayOfMonth": "30",
                        "@month": "11",
                        "@year": "2025",
                        "@hour": "12",
                        "@minute": "00",
                        "@second": "00",
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(successful_get_deposit_status_response_payload)


def get_pending_get_status_deposit_response(
    merchant_code: str,
    order_code: str,
) -> str:
    successful_get_deposit_status_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "paymentMethodDetail": {
                            "card": {
                                "@type": "debitcard",
                            }
                        },
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "CAPTURED",
                        "AuthorisationId": {"@id": "289567"},
                        "CVCResultCode": {"@description": "FAILED"},
                        "balance": {
                            "@accountType": "IN_PROCESS_CAPTURED",
                            "amount": {
                                "@value": str(
                                    int(to_minor_units(Decimal("2333.71"), "MXN"))
                                ),
                                "@currencyCode": "MXN",
                                "@exponent": "2",
                                "@debitCreditIndicator": "credit",
                            },
                        },
                        "instalments": "1",
                    },
                    "date": {
                        "@dayOfMonth": "30",
                        "@month": "11",
                        "@year": "2025",
                        "@hour": "12",
                        "@minute": "00",
                        "@second": "00",
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(successful_get_deposit_status_response_payload)


def get_successful_deposit_callback_payload(merchant_code: str, order_code: str) -> str:
    payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "notify": {
                "orderStatusEvent": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "paymentMethodDetail": {
                            "card": {
                                "@type": "debitcard",
                            }
                        },
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "SETTLED",
                        "AuthorisationId": {"@id": "289567"},
                        "CVCResultCode": {"@description": "FAILED"},
                        "balance": [
                            {
                                "@accountType": "SETTLED_BIBIT_NET",
                                "amount": {
                                    "@value": str(
                                        int(to_minor_units(Decimal("2033.70"), "MXN"))
                                    ),
                                    "@currencyCode": "MXN",
                                    "@exponent": "2",
                                    "@debitCreditIndicator": "credit",
                                },
                            },
                            {
                                "@accountType": "SETTLED_BIBIT_COMMISSION",
                                "amount": {
                                    "@value": str(
                                        int(to_minor_units(Decimal("300.01"), "MXN"))
                                    ),
                                    "@currencyCode": "MXN",
                                    "@exponent": "2",
                                    "@debitCreditIndicator": "credit",
                                },
                            },
                        ],
                        "instalments": "1",
                    },
                    "date": {
                        "@dayOfMonth": "30",
                        "@month": "11",
                        "@year": "2025",
                        "@hour": "12",
                        "@minute": "00",
                        "@second": "00",
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(payload)


def get_refused_get_status_deposit_response(
    merchant_code: str,
    order_code: str,
) -> str:
    refused_get_deposit_status_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "paymentMethodDetail": {
                            "card": {
                                "@type": "debitcard",
                            }
                        },
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "REFUSED",
                        "CVCResultCode": {"@description": "FAILED"},
                        "ISO8583ReturnCode": {
                            "@code": "5",
                            "@description": "REFUSED",
                        },
                        "instalments": 1,
                    },
                    "date": {
                        "@dayOfMonth": "30",
                        "@month": "11",
                        "@year": "2025",
                        "@hour": "12",
                        "@minute": "00",
                        "@second": "00",
                    },
                }
            },
        }
    }

    return generate_worldpay_xml(refused_get_deposit_status_response_payload)


def get_status_of_deposit_which_is_not_ready_yet_response(
    merchant_code: str,
    order_code: str,
) -> str:
    status_of_deposit_which_is_not_ready_yet_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "error": {
                        "@code": "5",
                        "#text": "Order not ready",
                    },
                },
            },
        },
    }

    return generate_worldpay_xml(
        status_of_deposit_which_is_not_ready_yet_response_payload
    )


def get_successful_get_status_withdraw_response(
    merchant_code: str, order_code: str
) -> str:
    successful_withdraw_callback_payload: dict[str, Any] = {}

    return generate_worldpay_xml(successful_withdraw_callback_payload)


def get_3ds_challenge_required_response(
    merchant_code: str,
    order_code: str,
    acs_url: str = "https://acs.example.com/3ds",
    payload: str = "test-cardinal-payload",
    transaction_id: str = "test-transaction-id-3ds",
    three_ds_version: str = "2.2.0",
) -> str:
    challenge_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "challengeRequired": {
                        "threeDSChallengeDetails": {
                            "acsURL": acs_url,
                            "payload": payload,
                            "transactionId3DS": transaction_id,
                            "threeDSVersion": three_ds_version,
                        }
                    },
                }
            },
        }
    }
    return generate_worldpay_xml(challenge_response_payload)


def get_3ds_challenge_required_response_v210(
    merchant_code: str,
    order_code: str,
) -> str:
    return get_3ds_challenge_required_response(
        merchant_code=merchant_code,
        order_code=order_code,
        three_ds_version="2.1.0",
    )


def get_deposit_finalize_success_response(
    merchant_code: str,
    order_code: str,
) -> str:
    finalize_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "AUTHORISED",
                        "AuthorisationId": {"@id": "289567"},
                        "CVCResultCode": {"@description": "MATCHED"},
                        "balance": {
                            "@accountType": "IN_PROCESS_AUTHORISED",
                            "amount": {
                                "@value": str(
                                    int(to_minor_units(Decimal("2333.71"), "MXN"))
                                ),
                                "@currencyCode": "MXN",
                                "@exponent": "2",
                                "@debitCreditIndicator": "credit",
                            },
                        },
                        "cardNumber": "4444********1111",
                        "instalments": "1",
                    },
                }
            },
        }
    }
    return generate_worldpay_xml(finalize_response_payload)


def get_deposit_finalize_failed_response(
    merchant_code: str,
    order_code: str,
) -> str:
    finalize_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "payment": {
                        "paymentMethod": "VISA-SSL",
                        "amount": {
                            "@value": str(
                                int(to_minor_units(Decimal("2333.71"), "MXN"))
                            ),
                            "@currencyCode": "MXN",
                            "@exponent": "2",
                            "@debitCreditIndicator": "credit",
                        },
                        "lastEvent": "REFUSED",
                        "CVCResultCode": {"@description": "FAILED"},
                        "ISO8583ReturnCode": {
                            "@code": "51",
                            "@description": "INSUFFICIENT FUNDS",
                        },
                        "instalments": 1,
                    },
                }
            },
        }
    }
    return generate_worldpay_xml(finalize_response_payload)


def get_payment_not_found_error_response(merchant_code: str, order_code: str) -> str:
    """Response when check_status is called before user completes 3DS."""
    error_response_payload = {
        "paymentService": {
            "@version": "1.4",
            "@merchantCode": merchant_code,
            "reply": {
                "orderStatus": {
                    "@orderCode": order_code,
                    "error": {
                        "@code": "5",
                        "#text": "Could not find payment for order",
                    },
                }
            },
        }
    }
    return generate_worldpay_xml(error_response_payload)
