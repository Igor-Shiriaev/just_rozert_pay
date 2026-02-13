import json
from typing import Any

from rozert_pay.common.metrics import track_duration
from rozert_pay.payment import models, types
from rozert_pay.payment.entities import UserData


@track_duration("customers.get_or_create_customer")
def get_or_create_customer(
    external_identity: types.ExternalCustomerId,
    user_data: UserData | None = None,
) -> models.Customer:
    assert external_identity

    customer, _ = models.Customer.objects.get_or_create(
        external_id=external_identity,
    )
    extra_data: dict[str, Any] = {}
    if customer.extra_encrypted is not None:
        extra_data = customer.extra_encrypted.get_secret_value() or {}
    user_data_history = extra_data.get("user_data_history", [])
    if user_data:
        d = json.loads(user_data.model_dump_json())
        if d not in user_data_history:
            user_data_history.append(d)

        extra = dict(extra_data or {})
        extra["user_data_history"] = user_data_history

        if user_data.email:
            customer.email_encrypted = user_data.email

        if user_data.phone:
            customer.phone_encrypted = user_data.phone

        if user_data.language:
            customer.language = user_data.language

        customer.extra_encrypted = extra

        customer.save()

    return customer
