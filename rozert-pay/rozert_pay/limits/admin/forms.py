import typing as ty

from django.forms import ModelForm
from rozert_pay.limits.models import CustomerLimit, MerchantLimit, MerchantLimitScope


class CustomerLimitForm(ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"


class MerchantLimitForm(ModelForm):
    class Meta:
        model = MerchantLimit
        fields = "__all__"
        help_texts = {
            "limit_type": "Select the limit type to configure the corresponding fields.",
        }

    def clean(self) -> dict[str, ty.Any]:
        cleaned_data = ty.cast(dict[str, ty.Any], super().clean())
        scope = cleaned_data.get("scope")
        if scope == MerchantLimitScope.MERCHANT:
            cleaned_data["wallet"] = None
        elif scope == MerchantLimitScope.WALLET:
            cleaned_data["merchant"] = None
        return cleaned_data
