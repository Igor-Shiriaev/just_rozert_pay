from uuid import uuid4

from rest_framework.exceptions import ErrorDetail
from rozert_pay.payment.api_v1.serializers import (
    WithdrawalTransactionRequestSerializer,
    user_data_serializers,
)


def test_user_data_custom_serializer():
    user_data_serializer = user_data_serializers.custom_user_data_serializer(
        "test", ["email", "phone"]
    )

    class S(WithdrawalTransactionRequestSerializer):
        user_data = user_data_serializer  # type: ignore[assignment]

    s = S(
        data={
            "wallet_id": str(uuid4()),
            "amount": 100,
            "currency": "USD",
            "withdraw_to_account": "123",
            "user_data": {},
        }
    )
    assert not s.is_valid()
    assert s.errors == {
        "user_data": {
            "email": [ErrorDetail(string="This field is required.", code="required")],
            "phone": [ErrorDetail(string="This field is required.", code="required")],
        }
    }
