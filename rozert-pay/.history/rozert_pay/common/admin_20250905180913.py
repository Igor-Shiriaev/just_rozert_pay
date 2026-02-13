import json

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.db import models
from django.forms.models import model_to_dict
from rozert_pay.account.models import User


class AdminLogFormMixin:
    """Logs create/update with a JSON snapshot of all non-M2M fields."""

    user: User | None = None

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def _log_admin_action(self, instance: models.Model, action_flag: int, verb: str, previous_state: dict = None):
        fields = [f.name for f in instance._meta.fields]  # excludes ManyToManyField
        current_state = model_to_dict(instance, fields=fields)

        if action_flag == CHANGE and previous_state:
            # Find changed fields
            changed_fields = {
                field: {"old": previous_state[field], "new": current_state[field]}
                for field in current_state
                if previous_state.get(field) != current_state[field]
            }
            
            change_message = json.dumps(
                {
                    "action": verb,
                    "user_id": getattr(self.user, "id", None),
                    "current_state": current_state,
                    "previous_state": previous_state,
                    "changed_fields": changed_fields
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        else:
            change_message = json.dumps(
                {
                    "action": verb,
                    "user_id": getattr(self.user, "id", None),
                    "current_state": current_state
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )

        LogEntry.objects.log_actions(
            user_id=getattr(self.user, "id", None),
            queryset=instance.__class__.objects.filter(pk=instance.pk),
            action_flag=action_flag,
            change_message=change_message,
        )

    def save(self, commit: bool = True):
        previous_state = instance
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        # Capture previous state for updates
        previous_state = None
        if is_update:
            previous_state = model_to_dict(
                instance.__class__.objects.get(pk=instance.pk)
            )

        if commit:
            instance.save()
            # No need to save_m2m() since we're not logging M2M,
            # but keeping it is harmless if form defines it.
            if hasattr(self, "save_m2m"):
                self.save_m2m()

            self._log_admin_action(
                instance=instance,
                action_flag=CHANGE if is_update else ADDITION,
                verb="updated" if is_update else "created",
                previous_state=previous_state,
            )
        return instance
