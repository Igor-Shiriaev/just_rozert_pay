import pytest
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


class TestValidationHelpers:
    @pytest.mark.parametrize(
        "account_number,expected",
        [
            ("02179006406029664", 2),
            ("13214587412547896", 3),
            ("00000000000000000", 0),
            (VALID_CLABE[:17], int(VALID_CLABE[17])),
        ],
    )
    def test_calculate_clabe_check_digit_valid(self, account_number, expected):
        result = calculate_clabe_check_digit(account_number)
        assert result == expected

    @pytest.mark.parametrize(
        "invalid_input",
        [
            "12345678901234567",
            "1234567890123456789",
        ],
    )
    def test_calculate_clabe_check_digit_invalid_length(self, invalid_input):
        with pytest.raises(ValueError, match="Account number must be 18 digits long"):
            calculate_clabe_check_digit(invalid_input)

    def test_validate_clabe(self, valid_clabe):
        assert validate_clabe(valid_clabe) == valid_clabe
        with pytest.raises(ValueError, match="Invalid CLABE"):
            validate_clabe(INVALID_CLABE)
        with pytest.raises(ValueError, match="CLABE must be 18 digits long"):
            validate_clabe("12345678901234567")
            validate_clabe("1234567890123456789")

    @freeze_time("2023-01-01")
    @pytest.mark.parametrize(
        "valid_curp",
        [
            MEXICAN_VALID_CURP,  # Has birthdate 00-12-30 (over 18 years old)
            MEXICAN_VALID_CURP2,  # Has birthdate 91-12-30 (over 18 years old)
        ],
    )
    def test_validate_mexican_curp_valid(self, valid_curp):
        assert validate_mexican_curp(valid_curp) == valid_curp

    @freeze_time("2023-01-01")
    @pytest.mark.parametrize(
        "invalid_curp",
        [
            INVALID_MEXICAN_CURP,  # Has birthdate 10-12-10 (under 18 at 2023-01-01)
        ],
    )
    def test_validate_mexican_curp_underage(self, invalid_curp):
        with pytest.raises(ValueError, match="User must be at least 18 years old"):
            validate_mexican_curp(invalid_curp)

    @pytest.mark.parametrize(
        "invalid_curp",
        [
            "ABC123",  # Too short
            "ABCDEFGHIJKLMNOPQRST",  # Too long
        ],
    )
    def test_validate_mexican_curp_invalid_length(self, invalid_curp):
        """Test validation of CURP with invalid length."""
        with pytest.raises(ValueError, match="CURP must be 18"):
            validate_mexican_curp(invalid_curp)

    @pytest.mark.parametrize(
        "invalid_curp",
        [
            MEXICAN_VALID_CURP[:4] + "A01230" + MEXICAN_VALID_CURP[10:],  # Letter in date
            MEXICAN_VALID_CURP[:4] + "991330" + MEXICAN_VALID_CURP[10:],  # Invalid month
        ],
    )
    def test_validate_mexican_curp_invalid_date_format(self, invalid_curp):
        """Test validation of CURP with invalid date format."""
        with pytest.raises(ValueError):
            validate_mexican_curp(invalid_curp)