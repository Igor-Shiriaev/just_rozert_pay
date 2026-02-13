import datetime
from decimal import Decimal
from typing import Union

from django.utils import formats  # type: ignore


def custom_localize(value: Union[datetime.datetime, datetime.date, Decimal], use_l10n: bool = None) -> str:
    if isinstance(value, datetime.datetime):
        # Return datetime with milliseconds precision,
        # See https://app.clubhouse.io/betmaster/story/36026/.
        # Changed due https://app.clubhouse.io/betmaster/story/45973/
        return value.strftime('%d-%m-%Y %H:%M:%S.%f')[:-3]
    if isinstance(value, datetime.date):
        # Changed due https://app.clubhouse.io/betmaster/story/45973/
        return value.strftime('%d-%m-%Y')
    return formats._real_localize(value, use_l10n)


formats._real_localize = formats.localize
formats.localize = custom_localize
