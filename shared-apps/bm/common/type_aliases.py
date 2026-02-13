from decimal import Decimal
from typing import TypedDict

AmountWithCurrencyDict = TypedDict('AmountWithCurrencyDict', {'value': Decimal, 'currency': str})
