from copy import deepcopy
from enum import Enum
from typing import Any, Optional, Tuple, Type

from bm.utils import enum_as_choices
from django.db.models import CharField, Model


def _patch_enum(enum: Type[Enum]) -> Type[Enum]:
    def __str__(self: Enum) -> str:
        return self.value

    def __len__(self: Enum) -> int:
        return len(self.value)

    enum.__str__ = __str__  # type: ignore
    enum.__len__ = __len__  # type: ignore
    return enum


class EnumCharField(CharField):
    def __init__(self, *args: Any, enum: Type[Enum], sort_enum: bool = False, **kwargs: Any) -> None:  # type: ignore
        self._enum = _patch_enum(deepcopy(enum))
        super().__init__(*args, **kwargs)
        if not self.choices:  # type: ignore[has-type]
            self.choices = enum_as_choices(enum, sort=sort_enum)

    def to_python(self, value: Any) -> Any:  # type: ignore
        if isinstance(value, str):
            value = self._enum(value)
        return value

    def get_prep_value(self, value: Any) -> Any:  # type: ignore
        value = super().get_prep_value(value)
        if isinstance(value, Enum):
            value = value.value
        return value

    def from_db_value(self, value: Optional[str], expression: Any, connection: Any) -> Optional[Enum]:  # type: ignore
        if value is None:
            return None
        try:
            return self._enum(value)
        except (KeyError, ValueError):
            # TODO: rise specific exception
            return value  # type: ignore

    def deconstruct(self) -> Tuple:
        name, path, args, kwargs = super().deconstruct()
        kwargs['enum'] = self._enum
        kwargs.pop('choices', None)
        return name, path, args, kwargs

    def validate(self, value: Any, model_instance: Model) -> None:
        super().validate(str(value), model_instance)
