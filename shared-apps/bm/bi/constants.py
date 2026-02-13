from bm.common.entities import StrEnum


class CashflowPeriod(StrEnum):
    CURRENT_WEEK = 'current_week'
    PREVIOUS_WEEK = 'previous_week'
    LAST_30_DAYS = 'last_30_days'
    LAST_YEAR = 'last_year'
    LIFETIME = 'lifetime'
