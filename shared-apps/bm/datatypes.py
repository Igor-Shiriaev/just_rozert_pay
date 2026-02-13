import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, Optional, Tuple, Union

from psycopg2._range import Range

from bm.typing_utils import T_Callable
from bm.serializers import serialize_decimal
from pydantic.dataclasses import dataclass


def _check_currency_compatibility(func: T_Callable) -> T_Callable:
    def wrapper(self, other: Optional['Money']):    # type: ignore
        if func.__name__ in ('__eq__', '__ne__') and not isinstance(other, self.__class__):
            return False
        assert isinstance(other, self.__class__), f'Incorrect value {other} of type {type(other)}'
        assert other.currency == self.currency, f'Other currency {other.currency} is not equal to {self.currency}'
        return func(self, other)
    return wrapper  # type: ignore


@dataclass
class Money:
    value: Decimal
    currency: str
    # converter: Callable[['Money', str], 'Money'] = field(init=False)

    if TYPE_CHECKING:
        def __init__(self, value: Any, currency: str) -> None: ...

    def __str__(self) -> str:
        return f'{self.value} {self.currency}'

    @classmethod
    def from_dict(cls, amount_dict: Any) -> 'Money':
        return cls(amount_dict['value'], amount_dict['currency'])

    def convert(self, to_currency: str) -> 'Money':
        from currency.utils import get_rates

        return self.__class__(
            value=get_rates().convert(
                amount=self.value,
                currency_from=self.currency,
                currency_to=to_currency,
            ),
            currency=to_currency,
        )

    def convert_or_scale(self, to_currency: str) -> 'Money':
        from currency.utils import convert_or_scale

        return self.__class__(
            value=convert_or_scale(
                amount=self.value,
                currency_from=self.currency,
                currency_to=to_currency,
            ),
            currency=to_currency,
        )

    def as_data(self) -> Tuple[Decimal, str]:
        return (self.value, self.currency)

    def to_dict(self) -> dict:
        return {
            'value': self.value,
            'currency': self.currency,
        }

    def __neg__(self):      # type: ignore
        return self.__class__(
            value=-self.value,
            currency=self.currency
        )

    @_check_currency_compatibility
    def __add__(self, other: 'Money') -> 'Money':
        return self.__class__(
            value=self.value + other.value,
            currency=self.currency
        )

    @_check_currency_compatibility
    def __sub__(self, other: 'Money') -> 'Money':
        return self.__class__(
            value=self.value - other.value,
            currency=self.currency
        )

    def __mul__(self, other: Union['Money', int, float, Decimal]) -> 'Money':
        if isinstance(other, (int, float, Decimal)):
            return self.__class__(
                value=self.value * Decimal(other),
                currency=self.currency
            )
        assert isinstance(other, self.__class__), str(other)
        assert other.currency == self.currency, 'Currency is not equal'
        return self.__class__(
            value=self.value * other.value,
            currency=self.currency
        )

    def __truediv__(self, other: Union['Money', int, float, Decimal]) -> 'Money':
        if isinstance(other, (int, float, Decimal)):
            return self.__class__(
                value=self.value / Decimal(other),
                currency=self.currency
            )
        assert isinstance(other, self.__class__), str(other)
        assert other.currency == self.currency, 'Currency is not equal'
        return self.__class__(
            value=self.value / other.value,
            currency=self.currency
        )

    def __floordiv__(self, other: Union['Money', int, float, Decimal]) -> 'Money':
        if isinstance(other, (int, float, Decimal)):
            return self.__class__(
                value=self.value // Decimal(other),
                currency=self.currency
            )
        assert isinstance(other, self.__class__), str(other)
        assert other.currency == self.currency, 'Currency is not equal'
        return self.__class__(
            value=self.value // other.value,
            currency=self.currency
        )

    def __bool__(self) -> bool:
        return bool(self.value)

    @_check_currency_compatibility
    def __lt__(self, other: 'Money') -> bool:
        return self.value < other.value

    @_check_currency_compatibility
    def __le__(self, other: 'Money') -> bool:
        return self.value <= other.value

    @_check_currency_compatibility
    def __eq__(self, other: Optional['Money']) -> bool: # type: ignore
        if other is None:
            return False
        return self.value == other.value

    @_check_currency_compatibility
    def __ne__(self, other: Optional['Money']) -> bool: # type: ignore
        if other is None:
            return False
        return self.value != other.value

    @_check_currency_compatibility
    def __gt__(self, other: 'Money') -> bool:
        return self.value > other.value

    @_check_currency_compatibility
    def __ge__(self, other: 'Money') -> bool:
        return self.value >= other.value

    def __abs__(self) -> 'Money':
        return self.__class__(  # type: ignore
            value=abs(self.value),
            currency=self.currency
        )

    def __json__(self) -> dict:
        return {
            'value': serialize_decimal(self.value),
            'currency': self.currency,
        }


class DateRange:
    def __init__(self, lower: datetime.date, upper: datetime.date):
        if lower > upper:
            raise ValueError('Start date should be less than end date')
        self.lower = lower
        self.upper = upper

    @classmethod
    def from_dates(cls, date1: datetime.date, date2: datetime.date) -> 'DateRange':
        lower = min(date1, date2)
        upper = max(date1, date2)
        return cls(lower, upper)

    def __json__(self) -> dict:
        return {
            'start_date': self.lower,
            'end_date': self.upper,
        }

    def __str__(self) -> str:
        return f'{self.lower} - {self.upper}'

    def __repr__(self) -> str:
        return f'DateRange({self.lower}, {self.upper})'

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, DateRange):
            return False
        return self.lower == other.lower and self.upper == other.upper

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, (datetime.date, datetime.datetime)):
            return self.lower <= item < self.upper
        elif isinstance(item, Range):
            return self.lower <= item.lower and item.upper <= self.upper
        raise TypeError('Item should be date or datetime tuple or DateRange object')



# Declares all service names as type. String values can be getted via ServiceNameType.__args__
ServiceNameType = Literal['messaging', 'promotion']
if hasattr(ServiceNameType, '__args__'):                                # type: ignore
    ServiceNames: Tuple[ServiceNameType] = ServiceNameType.__args__     # type: ignore
elif hasattr(ServiceNameType, '__values__'):                            # type: ignore
    ServiceNames: Tuple[ServiceNameType] = ServiceNameType.__values__   # type: ignore
else:
    raise TypeError('Cant define ServiceNames')


DecimalOrUnlimited = Union[Decimal, Literal['unlimited']]
GGRLimitBySportId = dict[int, DecimalOrUnlimited]
BetLimitBySportId = dict[int, DecimalOrUnlimited]
