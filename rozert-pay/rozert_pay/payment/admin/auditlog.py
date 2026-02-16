from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.utils.translation import gettext_lazy as _

from auditlog.admin import LogEntryAdmin
from auditlog.models import LogEntry


try:
    admin.site.unregister(LogEntry)
except NotRegistered:
    pass


@admin.register(LogEntry)
class LogEntryWithStatusReasonAdmin(LogEntryAdmin):
    readonly_fields = [
        *LogEntryAdmin.readonly_fields,
        "status_change_reason_code",
        "status_change_comment",
    ]
    fieldsets = [
        (None, {"fields": ["created", "user_url", "resource_url", "cid"]}),
        (
            _("Changes"),
            {"fields": ["action", "msg", "status_change_reason_code", "status_change_comment"]},
        ),
    ]

    @admin.display(description=_("Status change reason code"))
    def status_change_reason_code(self, obj: LogEntry) -> str:
        additional_data = obj.additional_data or {}
        status_change = additional_data.get("status_change")
        if not isinstance(status_change, dict):
            return "-"

        reason_code = status_change.get("reason_code")
        if not isinstance(reason_code, str) or not reason_code.strip():
            return "-"
        return reason_code

    @admin.display(description=_("Status change comment"))
    def status_change_comment(self, obj: LogEntry) -> str:
        additional_data = obj.additional_data or {}
        status_change = additional_data.get("status_change")
        if not isinstance(status_change, dict):
            return "-"

        comment = status_change.get("comment")
        if not isinstance(comment, str) or not comment.strip():
            return "-"
        return comment
