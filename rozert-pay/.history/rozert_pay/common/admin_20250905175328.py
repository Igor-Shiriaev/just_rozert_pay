class AdminLogFormMixin:
    """Logs create/update with a JSON snapshot of all non-M2M fields."""
    user: Optional[models.Model] = None

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def _log_admin_action(self, instance: models.Model, action_flag: int, verb: str):
        # Collect ONLY non-M2M fields (includes PK + non-editable)
        fields = [f.name for f in instance._meta.fields]  # excludes ManyToManyField
        snapshot = model_to_dict(instance, fields=fields)

        change_message = json.dumps(
            {"action": verb, "snapshot": snapshot},
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
        instance = super().save(commit=False)
        is_update = instance.pk is not None

        if commit:
            instance.save()
            # No need to save_m2m() since we’re not logging M2M,
            # but keeping it is harmless if form defines it.
            if hasattr(self, "save_m2m"):
                self.save_m2m()

            self._log_admin_action(
                instance=instance,
                action_flag=CHANGE if is_update else ADDITION,
                verb="updated" if is_update else "created",
            )
        return instance