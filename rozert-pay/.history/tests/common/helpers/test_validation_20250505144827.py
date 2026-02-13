import pytest
from rozert_pay.common.helpers.validation import calculate_clabe_check_digit, validate_clabe

def test_calculate_clabe_check_digit_valid():
    # Test case: CLABE from documentation
    test_cases = [
        {"account_number": "02179006406029664", "expected": 2},  # Valid CLABE from constants
        {"account_number": "13214587412547896", "expected": 3},  # Made up test case
        {"account_number": "00000000000000000", "expected": 0},  # Edge case - all zeros
    ]
    
    for case in test_cases:
        result = calculate_clabe_check_digit(case["account_number"])
        assert result == case["expected"]

def test_calculate_clabe_check_digit_invalid_length():
    # Test with invalid length
    with pytest.raises(ValueError, match="Account number must be 18 digits long"):
        calculate_clabe_check_digit("123456")
    
    with pytest.raises(ValueError, match="Account number must be 18 digits long"):
        calculate_clabe_check_digit("1234567890123456789")

def test_validate_clabe_valid():
    # Test with valid CLABE
    clabe = "021790064060296642"  # From constants.VALID_CLABE
    assert validate_clabe(clabe) == clabe

def test_validate_clabe_invalid():
    # Test with invalid CLABE - wrong check digit
    with pytest.raises(ValueError, match="Invalid CLABE"):
        validate_clabe("021790064060296643")  # From constants.INVALID_CLABE
    
    # Test with invalid length
    with pytest.raises(ValueError, match="CLABE must be 18 digits long"):
        validate_clabe("12345")