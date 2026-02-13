from django.forms import ModelForm
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit


class CustomerLimitForm(ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"


class MerchantLimitForm(ModelForm):
    max_overall_decline_percent = PercentageField(
        label="Max Overall Decline %",
        help_text="Maximum percentage of all declines (0-100%)",
        required=False,
    )
    max_withdrawal_decline_percent = PercentageField(
        label="Max Withdrawal Decline %",
        help_text="Maximum percentage of declined withdrawals (0-100%)",
        required=False,
    )
    max_deposit_decline_percent = PercentageField(
        label="Max Deposit Decline %",
        help_text="Maximum percentage of declined deposits (0-100%)",
        required=False,
    )
    max_ratio = PercentageField(
        label="Max Ratio %",
        help_text="Maximum percentage (0-100%)",
        required=False,
    )

    class Meta:
        model = MerchantLimit
        fields = "__all__"
        help_texts = {
            "limit_type": "Выберите тип лимита, чтобы настроить соответствующие поля.",
        }
