from django.forms import ModelForm
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit


class CustomerLimitForm(ModelForm):
    class Meta:
        model = CustomerLimit
        fields = "__all__"

    def save(self, commit: bool = True) -> CustomerLimit:
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        if is_update:
            event_logs.create_transaction_log(
                trx_id=alert.transaction.id,
                event_type=const.EventType.INFO,
                description="Limit alert acknowledged",
                extra={
                    "alert_id": alert.id,
                    "alert_status": alert.status,
                    "acknowledged_by": user.id,
                },
            )
            # Get the original values before saving
            original = CustomerLimit.objects.get(pk=instance.pk)
            changes = []

            # Check for changes in key fields
            for field in [
                "active",
                "description",
                "period",
                "max_successful_operations",
                "max_failed_operations",
                "min_operation_amount",
                "max_operation_amount",
                "total_successful_amount",
                "decline_on_exceed",
                "is_critical",
            ]:
                original_value = getattr(original, field)
                new_value = getattr(instance, field)
                if original_value != new_value:
                    changes.append(f"{field}: {original_value} -> {new_value}")

            if changes:
                logger.info(
                    f"CustomerLimit updated (ID: {instance.pk}, Customer: {instance.customer_id}): "
                    f"{'; '.join(changes)}"
                )
        else:
            logger.info(
                f"CustomerLimit created (Customer: {instance.customer_id}, "
                f"Period: {instance.period}, Active: {instance.active})"
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

    def save(self, commit: bool = True) -> MerchantLimit:
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        if is_update:
            # Get the original values before saving
            original = MerchantLimit.objects.get(pk=instance.pk)
            changes = []

            # Check for changes in key fields
            for field in [
                "active",
                "description",
                "scope",
                "limit_type",
                "period",
                "max_operations",
                "max_overall_decline_percent",
                "max_withdrawal_decline_percent",
                "max_deposit_decline_percent",
                "min_amount",
                "max_amount",
                "total_amount",
                "max_ratio",
                "burst_minutes",
                "decline_on_exceed",
                "is_critical",
            ]:
                original_value = getattr(original, field)
                new_value = getattr(instance, field)
                if original_value != new_value:
                    changes.append(f"{field}: {original_value} -> {new_value}")

            if changes:
                scope_info = (
                    f"Merchant: {instance.merchant_id}"
                    if instance.merchant_id
                    else f"Wallet: {instance.wallet_id}"
                )
                logger.info(
                    f"MerchantLimit updated (ID: {instance.pk}, {scope_info}): "
                    f"{'; '.join(changes)}"
                )
        else:
            scope_info = (
                f"Merchant: {instance.merchant_id}"
                if instance.merchant_id
                else f"Wallet: {instance.wallet_id}"
            )
            logger.info(
                f"MerchantLimit created ({scope_info}, Type: {instance.limit_type}, "
                f"Period: {instance.period}, Active: {instance.active})"
            )

        if commit:
            instance.save()
        return instance
