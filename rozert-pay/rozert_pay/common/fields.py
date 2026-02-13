from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db.models import CharField, DecimalField

if TYPE_CHECKING:
    _DecimalFieldBase = DecimalField[Decimal, Decimal]
    _CharFieldBase = CharField[str, str]
else:
    _DecimalFieldBase = DecimalField
    _CharFieldBase = CharField


class MoneyField(_DecimalFieldBase):
    MAX_DIGITS = 20 + 20
    DECIMAL_PLACES = 20

    def __init__(self, **kwargs: Any) -> None:
        if "max_digits" in kwargs:
            assert kwargs.pop("max_digits") == self.MAX_DIGITS

        if "decimal_places" in kwargs:
            assert kwargs.pop("decimal_places") == self.DECIMAL_PLACES

        super().__init__(
            max_digits=self.MAX_DIGITS,
            decimal_places=self.DECIMAL_PLACES,
            **kwargs,
        )


class CurrencyField(_CharFieldBase):
    MAX_LENGTH = 255

    def __init__(self, **kwargs: Any) -> None:
        if "max_length" in kwargs:
            assert kwargs.pop("max_length") == self.MAX_LENGTH
        super().__init__(max_length=self.MAX_LENGTH, **kwargs)
