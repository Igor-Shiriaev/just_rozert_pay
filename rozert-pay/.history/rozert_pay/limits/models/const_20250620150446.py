import datetime

from django.db.models import TextChoices


class LimitPeriod(TextChoices):
    ONE_HOUR = "1h", "1 Hour"
    TWENTY_FOUR_HOURS = "24h", "24 Hours"


def get_start_date_of_limit(
    trx_created_at: datetime.datetime, period: LimitPeriod | str
) -> datetime.datetime:
    if period == LimitPeriod.ONE_HOUR:
        return trx_created_at - datetime.timedelta(hours=1)
    elif period == LimitPeriod.TWENTY_FOUR_HOURS:
        return trx_created_at - datetime.timedelta(hours=24)
    else:
        raise ValueError(f"Invalid period: {period}")  # pragma: no cover
