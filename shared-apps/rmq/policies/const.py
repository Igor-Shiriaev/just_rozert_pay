from typing import Union

from bm.common.entities import StrEnum


class PolicyName(StrEnum):
    HA_EXACTLY_2 = 'HA-exactly-2'
    TTL_10_SEC = 'TTL-10sec'
    TTL_1_MIN = 'TTL-1min'
    TTL_10_MIN = 'TTL-10min'
    TTL_20_MIN = 'TTL-20min'
    TTL_6_HOUR = 'TTL-6hour'
    TTL_1_DAY = 'TTL-1day'
    TTL_3_DAY = 'TTL-3day'


POLICIES: dict[PolicyName, dict[str, Union[int, str]]] = {
    PolicyName.HA_EXACTLY_2: {
        'ha-mode': 'exactly',
        'ha-params': 2,
        'ha-sync-mode': 'automatic',
        'ha-promote-on-failure': 'always',
        'ha-promote-on-shutdown': 'when-synced',
    },
    PolicyName.TTL_10_SEC: {'message-ttl': 10 * 1000},
    PolicyName.TTL_1_MIN: {'message-ttl': 1 * 60 * 1000},
    PolicyName.TTL_10_MIN: {'message-ttl': 10 * 60 * 1000},
    PolicyName.TTL_20_MIN: {'message-ttl': 20 * 60 * 1000},
    PolicyName.TTL_6_HOUR: {'message-ttl': 1 * 6 * 60 * 60 * 1000},
    PolicyName.TTL_1_DAY: {'message-ttl': 1 * 24 * 60 * 60 * 1000},
    PolicyName.TTL_3_DAY: {'message-ttl': 3 * 24 * 60 * 60 * 1000},
}
