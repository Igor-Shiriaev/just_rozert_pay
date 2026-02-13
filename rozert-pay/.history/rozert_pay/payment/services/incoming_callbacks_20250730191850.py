from uuid import UUID

from django.conf import settings
from django.urls import reverse
from rozert_pay.common import const
from rozert_pay.payment.models import PaymentSystem


def get_rozert_callback_url(
    system: const.PaymentSystemType,
    trx_uuid: str | UUID | None = None,
) -> str:
    payment_system_slug = PaymentSystem.objects.get(type=system).slug
    url = reverse("callback", kwargs=dict(system=payment_system_slug))
    result = f"{settings.EXTERNAL_ROZERT_HOST}{url}"
    if trx_uuid:
        result = f"{result}?transaction_id={trx_uuid}"

    return result
