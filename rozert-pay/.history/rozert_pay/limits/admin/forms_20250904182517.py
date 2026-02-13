from decimal import Decimal
from typing import Any

from django.forms import DecimalField, ModelForm
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit


class PercentageField(DecimalField):
    """Custom field that displays percentage values as whole numbers (0-100) instead of decimals (0-1)"""
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault('max_digits', 5)
        kwargs.setdefault('decimal_places', 2)
        kwargs.setdefault('min_value', 0)
        kwargs.setdefault('max_value', 100)
        kwargs.setdefault('required', False)  # Make percentage fields not required by default
        super().__init__(*args, **kwargs)
    
    def to_python(self, value: Any) -> Any:
        """Convert percentage input (0-100) to decimal (0-1) for storage"""
        if value is None or value == '':
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


class CustomerLimitForm(ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"


class MerchantLimitForm(ModelForm):
    # Override percentage fields to display as percentages
    max_overall_decline_percent = PercentageField(
        label="Max Overall Decline %",
        help_text="Maximum percentage of all declines (0-100%)",
        required=False
    )
    max_withdrawal_decline_percent = PercentageField(
        label="Max Withdrawal Decline %", 
        help_text="Maximum percentage of declined withdrawals (0-100%)",
        required=False
    )
    max_deposit_decline_percent = PercentageField(
        label="Max Deposit Decline %",
        help_text="Maximum percentage of declined deposits (0-100%)",
        required=False
    )
    max_ratio = PercentageField(
        label="Max Ratio %", 
        help_text="Maximum percentage (0-100%)",
        required=False
    )

    class Meta:
        model = MerchantLimit
        fields = "__all__"
        help_texts = {
            "limit_type": "Выберите тип лимита, чтобы настроить соответствующие поля.",
        }
