from django.contrib import admin  # noqa
from django.contrib.admin.models import LogEntry

from .customer_limits import *  # noqa
from .limit_alert import *  # noqa
from .merchant_limits import *  # noqa

admin.site.register(LogEntry)
