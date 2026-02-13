from enum import Enum

from typing import Callable


class StrEnum(str, Enum):
    __iter__: Callable[..., 'StrEnum']  # type: ignore[assignment]

    def _generate_next_value_(name, start, count, last_values):  # type: ignore
        return name

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}.{self.name}'
