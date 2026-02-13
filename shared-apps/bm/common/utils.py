from datetime import timedelta
import re


def get_timedelta_from_str(timedelta_str: str) -> timedelta:
    delay_value, delay_type = re.findall(r'^(\d+)(m|h|d|ms|s)$', timedelta_str)[0]
    delay_value = int(delay_value)

    kw = {
        'm': 'minutes',
        'h': 'hours',
        'd': 'days',
        'ms': 'milliseconds',
        's': 'seconds',
    }[delay_type]
    return timedelta(**{kw: delay_value})
