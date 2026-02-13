from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.http import HttpRequest
from django.template import loader
from django.utils.safestring import mark_safe


class LocalHistoryMixin(admin.ModelAdmin):
    HISTORY_LIMIT = 5

    def get_readonly_fields(self, request: HttpRequest, obj: "models.Model" = None) -> list[str]:
        readonly_fields = super().get_readonly_fields(request, obj)
        return [*readonly_fields, "history"]

    @mark_safe
    def history(self, obj: "models.Model") -> str:
        all_history_elements = LogEntry.objects.filter(
            content_type_id=ContentType.objects.get_for_model(obj).pk,
            object_id=obj.pk,
        )
        total_history_elements = all_history_elements.count()
        history_elements = all_history_elements.order_by("-action_time")[: self.HISTORY_LIMIT]
        t = loader.get_template("admin/local_history.html")
        return t.render(
            {
                "current_object": obj,
                "history_elements": history_elements,
                "total_history_elements": total_history_elements,
                "opts": self.model._meta,
            }
        )
