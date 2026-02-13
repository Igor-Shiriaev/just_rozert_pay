from typing import Union, List

from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet, Model
from django.utils.encoding import force_str


def admin_log_change_bulk(
    queryset: Union[QuerySet, List[Model]],
    change_message: str,
    user_id: int = None
) -> None:
    if isinstance(queryset, QuerySet):  # type: ignore
        model = queryset.model
    elif len(queryset) > 0:
        model = queryset[0].__class__
    else:
        return None
    content_type = ContentType.objects.get_for_model(model, for_concrete_model=False)
    if user_id is None:
        user_id = get_user_model().objects.filter(
            is_active=True,
            is_staff=True,
            is_superuser=True
        ).values_list('pk', flat=True).first()
    log_entries = [LogEntry(
        user_id=user_id,
        content_type_id=content_type.pk,
        object_id=obj.pk,
        object_repr=force_str(obj)[:200],
        action_flag=CHANGE,
        change_message=change_message
    ) for obj in queryset]
    LogEntry.objects.bulk_create(log_entries)


def admin_log_change(
    obj: Model,
    change_message: str,
    user_id: int
) -> None:
    LogEntry.objects.log_action(
        user_id=user_id,
        content_type_id=ContentType.objects.get_for_model(obj, for_concrete_model=False).pk,
        object_id=obj.pk,
        object_repr=force_str(obj),
        action_flag=CHANGE,
        change_message=change_message
    )
