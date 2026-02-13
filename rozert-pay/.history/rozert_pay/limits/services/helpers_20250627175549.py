from typing import cast

from rozert_pay.limits import models as limit_models


def get_alerts_with_decline_on_exceed(
    all_triggered_limit_alerts: list[limit_models.LimitAlert],
) -> list[limit_models.LimitAlert]:
    return [
        alert
        for alert in all_triggered_limit_alerts
        if (
            alert.customer_limit
            and cast(limit_models.CustomerLimit, alert.customer_limit).decline_on_exceed
        )
        or (
            alert.merchant_limit
            and cast(limit_models.MerchantLimit, alert.merchant_limit).decline_on_exceed
        )
    ]
