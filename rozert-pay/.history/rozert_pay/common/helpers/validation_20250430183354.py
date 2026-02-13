def calculate_clabe_check_digit(account_number: str) -> int:
    """See https://stpmex.zendesk.com/hc/en-us/articles/360014675872-Calculation-of-the-CLABE-account-verification-digit"""
    if len(account_number) != 17:
        raise ValueError("Account number must be 18 digits long")

    ponderation = [3, 7, 1] * 6

    step1 = [int(account_number[i]) * ponderation[i] for i in range(17)]
    step2 = [x % 10 for x in step1]
    A = sum(step2)
    A = A % 10
    B = 10 - A
    control_digit = B % 10
    return control_digit
