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
    description = serializers.CharField(source="limit_description", read_only=True)
    limit_url = serializers.CharField(source="get_limit_admin_url", read_only=True)
    transaction_url = serializers.CharField(
        source="get_transaction_admin_url", read_only=True
    )

    class Meta:
        model = LimitAlert
        fields = (
            "id",
            "is_critical",
            "created_at",
            "description",
            "limit_url",
            "transaction_url",
        )
