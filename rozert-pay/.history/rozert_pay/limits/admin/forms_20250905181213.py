from django.forms import ModelForm
from rozert_pay.common.admin import AdminLogFormMixin
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit


class CustomerLimitForm(AdminLogFormMixin, ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"


class MerchantLimitForm(AdminLogFormMixin, ModelForm):
    class Meta:
        model = MerchantLimit
        fields = "__all__"
        help_texts = {
            "limit_type": "Выберите тип лимита, чтобы настроить соответствующие поля.",
        }
