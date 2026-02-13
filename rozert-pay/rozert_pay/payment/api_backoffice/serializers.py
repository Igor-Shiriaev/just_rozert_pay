from django.urls import reverse
from rest_framework import serializers
from rozert_pay.limits.models import LimitAlert
from rozert_pay.payment.models import DepositAccount, OutcomingCallback


class CabinetDepositAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepositAccount
        fields = (
            "created_at",
            "id",
            "customer_id",
            "unique_account_identifier",
            "wallet",
        )


class CabinetCallbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutcomingCallback
        fields = (
            "created_at",
            "id",
            "transaction",
            "callback_type",
            "target",
            "body",
            "status",
            "error",
            "last_attempt_at",
            "max_attempts",
            "current_attempt",
        )


class LimitAlertSerializer(serializers.ModelSerializer):
    description = serializers.SerializerMethodField()
    limit_url = serializers.SerializerMethodField()
    transaction_url = serializers.SerializerMethodField()
    text = serializers.SerializerMethodField()

    def get_text(self, obj: LimitAlert) -> str:
        extra = obj.extra or {}
        for key, value in extra.items():
            if isinstance(value, str) and " " in value:
                return f"{key}: {value}"
        return ""

    def get_description(self, obj: LimitAlert) -> str:
        if obj.customer_limit:
            return obj.customer_limit.description or "-"
        if obj.merchant_limit:
            return obj.merchant_limit.description or "-"
        return "-"

    def get_limit_url(self, obj: LimitAlert) -> str:
        if obj.customer_limit_id:
            return reverse(
                "admin:limits_customerlimit_change", args=[obj.customer_limit_id]
            )
        if obj.merchant_limit_id:
            return reverse(
                "admin:limits_merchantlimit_change", args=[obj.merchant_limit_id]
            )
        return "-"

    def get_transaction_url(self, obj: LimitAlert) -> str:
        if obj.transaction_id:
            return reverse(
                "admin:payment_paymenttransaction_change", args=[obj.transaction_id]
            )
        return "-"

    class Meta:
        model = LimitAlert
        fields = (
            "id",
            "is_critical",
            "created_at",
            "description",
            "limit_url",
            "transaction_url",
            "text",
        )
