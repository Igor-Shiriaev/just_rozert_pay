from urllib.parse import urlencode
from uuid import UUID

from django.conf import settings
from django.urls import reverse
from rozert_pay.common.metrics import track_duration
from rozert_pay.payment.models import PaymentSystem


@track_duration("incoming_callbacks.get_rozert_callback_url")
def get_rozert_callback_url(
    system: PaymentSystem,
    trx_uuid: str | UUID | None = None,
    wallet_uuid: str | UUID | None = None,
) -> str:
    payment_system_slug = system.slug
    url = reverse("callback", kwargs=dict(system=payment_system_slug))
    result = f"{settings.EXTERNAL_ROZERT_HOST}{url}"

    query_params: dict[str, str] = {}
    if trx_uuid:
        query_params["transaction_uuid"] = str(trx_uuid)
    if wallet_uuid:
        query_params["wallet_uuid"] = str(wallet_uuid)

    if query_params:
        result = f"{result}?{urlencode(query_params)}"

    return result
