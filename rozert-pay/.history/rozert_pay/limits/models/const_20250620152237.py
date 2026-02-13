import datetime

from django.db.models import TextChoices


class LimitPeriod(TextChoices):
    ONE_HOUR = "1h", "1 Hour"
    TWENTY_FOUR_HOURS = "24h", "24 Hours"
    BEGINNING_OF_DAY = "beginning_of_day", "Beginning of Day"
    BEGINNING_OF_WEEK = "beginning_of_week", "Beginning of Week"
