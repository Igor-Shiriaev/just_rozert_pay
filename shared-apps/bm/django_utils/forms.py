from enum import Enum
from typing import Type, Any, Optional

from django import forms


class EnumField(forms.ChoiceField):
    def __init__(self, enum_class: Type[Enum], *args: Any, **kwargs: Any) -> None:
        self._enum = enum_class
        super().__init__(*args, **kwargs)
        self.choices = [(e.value, e.value) for e in enum_class]

    def validate(self, value: Enum) -> None:
        if value not in self._enum:
            raise forms.ValidationError(
                f"{value} is not a valid value for {self._enum.__name__}"
            )

    def to_python(self, value: Optional[str]) -> Optional[Enum]:
        if value is not None:
            return self._enum(value)
        return None
