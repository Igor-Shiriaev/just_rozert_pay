from decimal import Decimal
from typing import Any

from django.forms import DecimalField


class PercentageField(DecimalField):
    """Custom field that displays percentage values as whole numbers (0-100) instead of decimals (0-1)"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 5)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("min_value", 0)
        kwargs.setdefault("max_value", 100)
        super().__init__(*args, **kwargs)

    def to_python(self, value: Any) -> Any:
        """Convert percentage input (0-100) to decimal (0-1) for storage"""
        if value is None or value == "":
            return None
        value = super().to_python(value)
        if value is not None:
            return value / 100
        return value

    def prepare_value(self, value: Any) -> Any:
        """Convert decimal value (0-1) to percentage (0-100) for display"""
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value * 100
        return value