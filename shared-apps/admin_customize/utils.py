import copy
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, Optional, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.utils.timezone import localtime


def add_param_to_url(url: str, add: dict[str, Any] = None, remove: list[str] = None) -> str:
    add = add or {}
    remove = remove or []
    parts = list(urlparse(url))
    query = dict(parse_qsl(parts[4]))
    for k in remove:
        query.pop(k, None)
    query.update(add)
    parts[4] = urlencode(query)
    return str(urlunparse(parts))


def humanize_string(source_string: str, html: bool = False, title: bool = False) -> str:
    """
    Make a verbose string from a source string.
    :param source_string: The source string to make verbose.
    :param html: If True, replace spaces with &nbsp;.
    :param title: If True, capitalize each word.
    :return: The verbose string.

    >>> humanize_string('hello_world')
    'Hello World'
    >>> humanize_string('hello_world',html=True)
    'Hello&nbsp;World'
    >>> humanize_string('HELLO_WORLD')
    'Hello World'
    >>> humanize_string('helloWorld')
    'Hello World'
    >>> humanize_string('HelloWorld',html=True)
    'Hello&nbsp;World'
    """
    text = re.sub(r'[_-]+', ' ', source_string)
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    text = text.strip().lower()
    text = text.capitalize()
    if title:
        text = text.title()
    else:
        text = text.capitalize()

    if html:
        text = text.replace(' ', '&nbsp;')
    return text


VERBOSE_DATE_FORMAT = '%B %d, %Y'
DIGITAL_DATE_FORMAT = '%d.%m.%Y'
TIME_FORMAT = '%H:%M:%S'


def humanize_date(value: Union[datetime, date], digital: bool = True) -> str:
    """
    Convert a datetime or date object to a human-readable string.
    :param value: The datetime or date object to convert.
    :param digital: If True, return the date in 'YYYY-MM-DD' format; otherwise, return in 'Month Day, Year' format.
    :return: A human-readable string representation of the date.

    >>> from datetime import datetime
    >>> humanize_date(datetime(2023, 10, 1))
    '2023-10-01'
    >>> from datetime import date
    >>> humanize_date(date(2023, 10, 1))
    '2023-10-01'
    >>> humanize_date(datetime(2023, 10, 1), digital=False)
    'October 1, 2023'
    >>> humanize_date(date(2023, 10, 1), digital=False)
    'October 1, 2023'
    """
    template_str = DIGITAL_DATE_FORMAT if digital else VERBOSE_DATE_FORMAT
    if not isinstance(value, (datetime, date)):
        raise ValueError("Value must be a datetime or date object.")
    return value.strftime(template_str)


def humanize_time(value: datetime) -> str:
    """
    Convert a datetime object to a human-readable time string.
    :param value: The datetime object to convert.
    :return: A human-readable string representation of the time.

    >>> from datetime import datetime
    >>> humanize_time(datetime(2023, 10, 1, 14, 30))
    '14:30'
    """
    if not isinstance(value, datetime):
        raise ValueError("Value must be a datetime object.")
    return value.strftime(TIME_FORMAT)


def humanize_datetime(value: datetime, digital: bool = True, localize: bool = False) -> str:
    """
    Convert a datetime object to a human-readable string.
    :param value: The datetime object to convert.
    :param digital: If True, return the date in 'YYYY-MM-DD HH:MM:SS' format; otherwise, return in 'Month Day, Year HH:MM AM/PM' format.
    :param localize: If True, localize the datetime to the current timezone before formatting.
    :return: A human-readable string representation of the datetime.

    >>> from datetime import datetime
    >>> humanize_datetime(datetime(2023, 10, 1, 14, 30))
    '01.10.2023 14:30:00'
    >>> humanize_datetime(datetime(2023, 10, 1, 14, 30), digital=False)
    'October 1, 2023 14:30:00'

    """
    if localize:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = localtime(value)
    template_str = (
        f'{DIGITAL_DATE_FORMAT} {TIME_FORMAT}'
        if digital
        else f'{VERBOSE_DATE_FORMAT} {TIME_FORMAT}'
    )
    if not isinstance(value, datetime):
        raise ValueError("Value must be a datetime object.")
    return value.strftime(template_str)


def humanize_timedelta(delta: timedelta) -> str:
    """
    Convert a timedelta object to a human-readable string.
    :param delta: The timedelta object to convert.
    :return: A human-readable string representation of the timedelta.

    >>> from datetime import timedelta
    >>> humanize_timedelta(timedelta(days=2, hours=3, minutes=15))
    '2 days, 3 hours, 15 minutes'
    >>> humanize_timedelta(timedelta(hours=1, minutes=30))
    '1 hour, 30 minutes'
    >>> humanize_timedelta(timedelta(minutes=45))
    '45 minutes'
    >>> humanize_timedelta(timedelta(seconds=30))
    '30 seconds'
    """
    if not isinstance(delta, timedelta):
        raise ValueError("Value must be a timedelta object.")
    total_seconds = int(delta.total_seconds())
    periods = [
        ('year', 31536000),  # 60 * 60 * 24 * 365
        ('day', 86400),  # 60 * 60 * 24
        ('hour', 3600),  # 60 * 60
        ('minute', 60),
        ('second', 1),
    ]

    strings = []
    for period_name, period_seconds in periods:
        if total_seconds >= period_seconds:
            period_value, total_seconds = divmod(total_seconds, period_seconds)
            if period_value > 0:
                strings.append(f"{period_value} {period_name}{'s' if period_value > 1 else ''}")

    return ', '.join(strings) if strings else '0 seconds'


def update_fieldsets(
    fieldsets: tuple,
    section_name: Union[str, tuple[str, str], Literal['*']],
    *,
    fields_to_add: Optional[list[str | tuple[str, ...]]] = None,
    fields_to_remove: Optional[list[str | tuple[str, ...]]] = None,
) -> tuple:
    new_fieldsets = copy.deepcopy(fieldsets)
    for section, section_data in new_fieldsets:
        should_update = (
            section_name == '*'
            or (isinstance(section_name, str) and section == section_name)
            or (isinstance(section_name, tuple) and section_name in section)
        )
        if should_update:
            if fields_to_add:
                section_data['fields'] += tuple(fields_to_add)
            if fields_to_remove:
                section_data['fields'] = tuple(
                    filter(
                        lambda el: el not in fields_to_remove,  # type: ignore[arg-type]
                        section_data['fields'],
                    )
                )
    return tuple(new_fieldsets)


def flatten_dict(
    source: dict[str, Any],
    parent_key: str = "",
    sep: str = ".",
) -> dict[str, Any]:
    items: dict[str, Any] = {}
    for k, v in source.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items
