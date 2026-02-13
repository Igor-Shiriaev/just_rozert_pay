from uuid import uuid4

from django.db.models import F, Q
from rozert_pay.payment import models, types
from rozert_pay.payment.entities import UserData


def get_or_create_customer(
    external_identity: types.ExternalCustomerId | None,
    user_data: UserData | None = None,
) -> models.Customer | None:
    if not external_identity and not user_data:
        return None

    query = Q()
    if external_identity:
        query |= Q(external_id=external_identity)

    email = phone = None
    if user_data:
        if email := user_data.email:
            query |= Q(email=email)

        if phone := user_data.phone:
            query |= Q(phone=phone)

    # Customers with external identity first
    customers = list(
        models.Customer.objects.filter(query).order_by(
            F("external_id").desc(nulls_last=True)
        )
    )
    if customers:
        return customers[0]

    print('1111111111111111111', external_identity, email, phone)
    return models.Customer.objects.create(
        external_id=external_identity or str(uuid4()),
        email=email,
        phone=phone,
        language=user_data.language if user_data else None,
        extra={
            "user_data": user_data.model_dump() if user_data else None,
        },
    )
