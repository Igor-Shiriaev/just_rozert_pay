from django.urls import reverse
from rozert_pay.common.metrics import track_duration
from rozert_pay.limits.models import LimitAlert
from rozert_pay.settings import EXTERNAL_ROZERT_HOST


from pydantic import BaseModel, ConfigDict
from rozert_pay.limits.models import CustomerLimit, LimitAlert, MerchantLimit
from rozert_pay.settings import EXTERNAL_ROZERT_HOST


class FilteredOutLimit(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    limit: CustomerLimit | MerchantLimit
    reason: str | None


@track_duration("limits.utils.construct_notification_message")
def construct_notification_message(alerts: list[LimitAlert]) -> str:
    messages = []
    for alert in alerts:
        trigger_time = alert.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        admin_url = f"{EXTERNAL_ROZERT_HOST}{reverse('admin:limits_limitalert_change', args=[alert.id])}"

        if alert.customer_limit:
            category = "💢 Critical" if alert.is_critical else "Regular"
            description = alert.customer_limit.description
            wallet_name = "N/A"
            alert_type = "Customer Limit"
            period = alert.customer_limit.period
        elif alert.merchant_limit:
            category = "💢 Critical" if alert.is_critical else "Regular"
            description = alert.merchant_limit.description or "Merchant Limit"
            wallet_name = (
                alert.merchant_limit.wallet.name
                if alert.merchant_limit.wallet
                else "N/A"
            )
            alert_type = alert.merchant_limit.scope
            period = alert.merchant_limit.period
        else:
            raise ValueError("Invalid alert type")  # pragma: no cover

        message = (
            f"Text: {_get_text_payload_of_extra(alert.extra)}\n"
            f"Trigger time: {trigger_time}\n"
            f"Category: {category}\n"
            f"Description: {description}\n"
            f"Wallet name: {wallet_name}\n"
            f"Type: {alert_type}\n"
            f"Period: {period}\n"
            f"ID: <{admin_url}|{alert.id}>"
        )

        messages.append(message)

    return "\n\n".join(messages)


@track_duration("limits.utils._get_text_payload_of_extra")
def _get_text_payload_of_extra(extra: dict[str, str]) -> str:
    for key, value in extra.items():
        if " " in value:
            return f"{key}: {value}"
    return ""
