from django.db.models import TextChoices


class LimitPeriod(TextChoices):
    ONE_HOUR = "1h", "1 Hour"
    TWENTY_FOUR_HOURS = "24h", "24 Hours"
    BEGINNING_OF_HOUR = "beginning_of_hour", "Beginning of Hour"
    BEGINNING_OF_DAY = "beginning_of_day", "Beginning of Day"


class SlackChannel(TextChoices):
    FOR_REGULAR_LIMITS = "for_regular_limits", "For Regular Limits"
    FOR_CRITICAL_LIMITS = "for_critical_limits", "For Critical Limits"
