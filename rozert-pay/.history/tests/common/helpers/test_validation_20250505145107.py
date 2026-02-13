import pytest
from rozert_pay.common.helpers.validation import (
    calculate_clabe_check_digit,
    validate_clabe,
)

import pytest
from datetime import datetime, timedelta
from django.utils import timezone
from freezegun import freeze_time

from rozert_pay.common.helpers.validation import (
    calculate_clabe_check_digit,
    validate_mexican_curp,
    validate_clabe,
)
from tests.payment.systems.d24_mercadopago.constants import (
    MEXICAN_VALID_CURP,
    MEXICAN_VALID_CURP2,
    INVALID_MEXICAN_CURP,
    VALID_CLABE,
    INVALID_CLABE,
)


class TestCalculateClabeCheckDigit:
    def test_calculate_clabe_check_digit_valid(self):
        """Test the calculation of CLABE check digit with valid input."""
        # Test with valid CLABE from test constants
        assert calculate_clabe_check_digit(VALID_CLABE[:17]) == int(VALID_CLABE[17])
        
        # Additional test cases
        test_cases = [
            {"account_number": "02179006406029664", "expected": 2},
            {"account_number": "13214587412547896", "expected": 3},
            {"account_number": "00000000000000000", "expected": 0},
        ]
        
        for case in test_cases:
            result = calculate_clabe_check_digit(case["account_number"])
            assert result == case["expected"]

    def test_calculate_clabe_check_digit_invalid_length(self):
        """Test the function with invalid length input."""
        with pytest.raises(ValueError, match="Account number must be 18 digits long"):
            calculate_clabe_check_digit("123456")
        
        with pytest.raises(ValueError, match="Account number must be 18 digits long"):
            calculate_clabe_check_digit("1234567890123456789")

    def test_calculate_clabe_check_digit_non_numeric(self):
        """Test the function with non-numeric input."""
        with pytest.raises(ValueError):
            calculate_clabe_check_digit("1234567890123456a")


class TestValidateClabe:
    def test_validate_clabe_valid(self):
        """Test validation of a valid CLABE."""
        assert validate_clabe(VALID_CLABE) == VALID_CLABE

    def test_validate_clabe_invalid_checksum(self):
        """Test validation of CLABE with invalid checksum."""
        with pytest.raises(ValueError, match="Invalid CLABE"):
            validate_clabe(INVALID_CLABE)

    def test_validate_clabe_invalid_length(self):
        """Test validation of CLABE with invalid length."""
        with pytest.raises(ValueError, match="CLABE must be 18 digits long"):
            validate_clabe("12345")
        
        with pytest.raises(ValueError, match="CLABE must be 18 digits long"):
            validate_clabe("1234567890123456789")


class TestValidateMexicanCurp:
    @freeze_time("2023-01-01")
    def test_validate_mexican_curp_valid(self):
        """Test validation of valid CURP."""
        # MEXICAN_VALID_CURP has birthdate 00-12-30 (over 18 years old)
        assert validate_mexican_curp(MEXICAN_VALID_CURP) == MEXICAN_VALID_CURP
        # MEXICAN_VALID_CURP2 has birthdate 91-12-30 (over 18 years old)
        assert validate_mexican_curp(MEXICAN_VALID_CURP2) == MEXICAN_VALID_CURP2

    @freeze_time("2023-01-01")
    def test_validate_mexican_curp_underage(self):
        """Test validation of CURP for underage person."""
        # INVALID_MEXICAN_CURP has birthdate 10-12-10 (under 18 years old at 2023-01-01)
        with pytest.raises(ValueError, match="User must be at least 18 years old"):
            validate_mexican_curp(INVALID_MEXICAN_CURP)

    def test_validate_mexican_curp_invalid_length(self):
        """Test validation of CURP with invalid length."""
        with pytest.raises(ValueError, match="CURP must be 18"):
            validate_mexican_curp("ABC123")
        
        with pytest.raises(ValueError, match="CURP must be 18"):
            validate_mexican_curp("ABCDEFGHIJKLMNOPQRST")

    def test_validate_mexican_curp_invalid_date_format(self):
        """Test validation of CURP with invalid date format."""
        # Replace digits in birthdate part with letters
        invalid_date_curp = MEXICAN_VALID_CURP[:4] + "A01230" + MEXICAN_VALID_CURP[10:]
        with pytest.raises(ValueError):
            validate_mexican_curp(invalid_date_curp)
