from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.forms import ModelForm
from django.forms.models import model_to_dict
from rozert_pay.common.admin import AdminLogFormMixin
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit


class CustomerLimitForm(AdminLogFormMixin, ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"

    def save(self, commit: bool = True) -> CustomerLimit:
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        # Capture previous state at the beginning
        previous_state = None
        if is_update:
            previous_state = model_to_dict(CustomerLimit.objects.get(pk=instance.pk))

        if commit:
            instance.save()

            action_flag = CHANGE if is_update else ADDITION
            text_action = "updated" if is_update else "created"

            # Create comprehensive change message
            current_state = model_to_dict(instance)

            if is_update and previous_state:
                # Find changed fields
                changed_fields = {
                    field: {"old": previous_state[field], "new": current_state[field]}
                    for field in current_state
                    if previous_state.get(field) != current_state[field]
                }

                change_message = f"Customer Limit {text_action} by {self.user.id}\n\nPrevious: {previous_state}\nCurrent: {current_state}\nChanged: {changed_fields}"
            else:
                change_message = (
                    f"Customer Limit {text_action} by {self.user.id}\n\n{current_state}"
                )

            LogEntry.objects.log_actions(
                user_id=self.user.id,
                queryset=CustomerLimit.objects.all(),
                action_flag=action_flag,
                change_message=change_message,
            )

        return instance


class MerchantLimitForm(AdminLogFormMixin, ModelForm):
    class Meta:
        model = MerchantLimit
        fields = "__all__"
        help_texts = {
            "limit_type": "Выберите тип лимита, чтобы настроить соответствующие поля.",
        }

    def save(self, commit: bool = True) -> MerchantLimit:
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        # Capture previous state at the beginning
        previous_state = None
        if is_update:
            previous_state = model_to_dict(MerchantLimit.objects.get(pk=instance.pk))

        if commit:
            instance.save()

            action_flag = CHANGE if is_update else ADDITION
            text_action = "updated" if is_update else "created"

            # Create comprehensive change message
            current_state = model_to_dict(instance)

            if is_update and previous_state:
                # Find changed fields
                changed_fields = {
                    field: {"old": previous_state[field], "new": current_state[field]}
                    for field in current_state
                    if previous_state.get(field) != current_state[field]
                }

                change_message = f"Merchant Limit {text_action} by {self.user.id}\n\nPrevious: {previous_state}\nCurrent: {current_state}\nChanged: {changed_fields}"
            else:
                change_message = (
                    f"Merchant Limit {text_action} by {self.user.id}\n\n{current_state}"
                )

            LogEntry.objects.log_actions(
                user_id=self.user.id,
                queryset=MerchantLimit.objects.all(),
                action_flag=action_flag,
                change_message=change_message,
            )

        return instance
