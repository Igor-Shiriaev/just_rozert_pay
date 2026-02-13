from django.forms import ModelForm
from rozert_pay.common import const
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit
from rozert_pay.payment.services import event_logs
from django.forms.models import model_to_dict


class CustomerLimitForm(ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def save(self, commit: bool = True) -> CustomerLimit:
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        if is_update:
            description = f"Customer Limit updated by {self.user.id}"
        else:
            description = f"Customer Limit created by {self.user.id}"
        event_logs.create_event_log(
            event_type=const.EventType.UPDATE_LIMIT,
            description=description,
            extra=model_to_dict(instance),
            system_type=None,
            customer=None,
            merchant=None,
        )

        if commit:
            instance.save()
        return instance


class MerchantLimitForm(ModelForm):
    class Meta:
        model = MerchantLimit
        fields = "__all__"
        help_texts = {
            "limit_type": "Выберите тип лимита, чтобы настроить соответствующие поля.",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def save(self, commit: bool = True) -> MerchantLimit:
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        if is_update:
            description = f"Customer Limit updated by {self.user.id}"
        else:
            description = f"Customer Limit created by {self.user.id}"
        event_logs.create_event_log(
            event_type=const.EventType.UPDATE_LIMIT,
            description=description,
            extra=model_to_dict(instance),
            system_type=None,
            customer=None,
            merchant=None,
        )

        if commit:
            instance.save()
        return instance

        if commit:
            instance.save()
        return instance
