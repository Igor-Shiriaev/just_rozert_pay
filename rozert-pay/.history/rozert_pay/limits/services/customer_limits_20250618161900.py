from rozert_pay.limits import models as limit_models
from rozert_pay.payment.services import db_services


def get_active_limits() -> (
    list[limit_models.CustomerLimit | limit_models.MerchantLimit]
):
    # TODO: cache in memory for 1 min
    return list(limit_models.CustomerLimit.objects.filter(status=True)) + list(
        limit_models.MerchantLimit.objects.filter(status=True)
    )


def on_transaction(
    trx: "db_services.LockedTransaction",
) -> tuple[bool, list[limit_models.LimitAlerts]]:
    """
    Returns: (is_transaction_declined, created_alerts)
    Проходим по всем активным лимитам, смотрим какие подходят
    Создаем LimitAlert
    Если нужно деклайним транзакцию
    id транзакции нужно привязать к LimitAlerts
    В limit alerts нужно сохранять все стат данные которые использовались для триггеринга лимита
    Стат данные не кешируем
    """