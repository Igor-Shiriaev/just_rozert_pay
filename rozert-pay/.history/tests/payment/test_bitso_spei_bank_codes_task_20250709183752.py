import logging
from unittest.mock import Mock, patch

import pytest
import requests
from rozert_pay.payment.models import Bank, PaymentCardBank
from rozert_pay.payment.systems.bitso_spei.models import BitsoSpeiCardBank
from rozert_pay.payment.tasks import check_bitso_spei_bank_codes


@pytest.fixture
def mock_bitso_api_response() -> dict:
    """Valid Bitso API response."""
    return {
        "success": True,
        "payload": [
            {
                "code": "40012",
                "name": "BBVA Bancomer",
                "countryCode": "MX",
                "isActive": True,
            },
            {
                "code": "40014",
                "name": "Santander",
                "countryCode": "MX",
                "isActive": False,
            },
            {
                "code": "40138",
                "name": "Banco Azteca",
                "countryCode": "MX",
                "isActive": True,
            },
        ],
    }


@pytest.fixture
def mock_payment_card_banks() -> list[PaymentCardBank]:
    """Create PaymentCardBank instances for testing."""
    bank1 = Bank.objects.create(name="BBVA Bancomer Test Bank")
    bank2 = Bank.objects.create(name="Santander Test Bank")

    return [
        PaymentCardBank.objects.create(
            bin=123456,
            bank=bank1,
            country="MX",
        ),
        PaymentCardBank.objects.create(
            bin=654321,
            bank=bank2,
            country="MX",
        ),
    ]


