from django.forms import ModelForm
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit


class CustomerLimitForm(ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"

    # def clean(self):
    #     cleaned_data = super().clean()
    #     customer = cleaned_data.get("customer")
    #     period = cleaned_data.get("period")

    #     if not customer:
    #         self.add_error("customer", _("The 'Customer' field is required"))

    #     if customer and period:
    #         qs = CustomerLimit.objects.filter(customer=customer, period=period)
    #         if self.instance.pk:
    #             qs = qs.exclude(pk=self.instance.pk)
    #         if qs.exists():
    #             self.add_error("period", _("Limit for this customer with this period already exists"))

    #     if not any(
    #         cleaned_data.get(f) for f in [
    #             "max_successful_operations",
    #             "max_failed_operations",
    #             "min_operation_amount",
    #             "max_operation_amount",
    #             "total_successful_amount",
    #         ]
    #     ):
    #         self.add_error(None, _("At least one of the limit fields must be set."))

    #     return cleaned_data


class MerchantLimitForm(ModelForm):
    class Meta:
        model = MerchantLimit
        fields = "__all__"
        help_texts = {
            "limit_type": "Выберите тип лимита, чтобы настроить соответствующие поля.",
        }
