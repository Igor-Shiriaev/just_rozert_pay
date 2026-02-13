from django.db.models import TextChoices


class LimitPeriod(TextChoices):
    ONE_HOUR = "1h", "1 Hour"
    TWENTY_FOUR_HOURS = "24h", "24 Hours"
    BEGINNING_OF_HOUR = "beginning_of_hour", "Beginning of Hour"
    BEGINNING_OF_DAY = "beginning_of_day", "Beginning of Day"


SLACK_CHANNEL_NAME_REGULAR_LIMITS = "limits-regular"
SLACK_CHANNEL_NAME_CRITICAL_LIMITS = "limits-critical"