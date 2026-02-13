from django.forms import ModelForm
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit
from django.contrib.contenttypes.models import ContentType
from django.utils.encoding import force_str


class CustomerLimitForm(ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def save(self, commit: bool = True) -> CustomerLimit:
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        if commit:
            instance.save()

            # Log the action using LogEntry
            action_flag = CHANGE if is_update else ADDITION
            change_message = f"Customer Limit {'updated' if is_update else 'created'} by {self.user.id}"

            LogEntry.objects.log_actions(
                user_id=self.user.id,
                content_type_id=ContentType.objects.get_for_model(instance).pk,
                object_id=instance.pk,
                object_repr=force_str(instance),
                action_flag=action_flag,
                change_message=change_message,
            )

        return instance


class MerchantLimitForm(ModelForm):
    class Meta:
        model = MerchantLimit
        fields = "__all__"
        help_texts = {
            "limit_type": "Выберите тип лимита, чтобы настроить соответствующие поля.",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def save(self, commit: bool = True) -> MerchantLimit:
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        if commit:
            instance.save()

            # Log the action using LogEntry
            action_flag = CHANGE if is_update else ADD
            change_message = f"Merchant Limit {'updated' if is_update else 'created'} by {self.user.id}"

            LogEntry.objects.log_action(
                user_id=self.user.id,
                content_type_id=ContentType.objects.get_for_model(instance).pk,
                object_id=instance.pk,
                object_repr=force_str(instance),
                action_flag=action_flag,
                change_message=change_message,
            )

        return instance
