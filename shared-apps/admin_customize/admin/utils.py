import functools
from typing import Any, Callable, TypeVar

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import Model, QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils.encoding import force_str

try:
    from django.db.models import JSONField
except ImportError:
    from django.contrib.postgres.fields import JSONField  # type: ignore[no-redef]  # noqa: F401

T = TypeVar('T', bound=Callable)


# TODO: move logic to BaseAdminMeta?
def adminview_permission_required(view_func: T) -> T:
    @functools.wraps(view_func)
    def on_call(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:  # type: ignore
        permission_name = '{app_label}.adminview_{model_name}_{view_name}'.format(
            app_label=self.opts.app_label,
            model_name=self.opts.model.__name__.lower(),
            view_name=view_func.__name__,
        )
        if not request.user.has_perm(permission_name):
            raise PermissionDenied()
        return view_func(self, request, *args, **kwargs)

    return on_call  # type: ignore


CUSTOM_ADMIN_PERMISSION_ATTR = 'custom_admin_permission'


def custom_admin_permission_required(permission_name: str) -> Callable[[T], T]:
    def decorator(view_func: T) -> T:
        @functools.wraps(view_func)
        def on_call(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:  # type: ignore
            if not request.user.has_perm(permission_name):
                raise PermissionDenied()
            return view_func(self, request, *args, **kwargs)

        setattr(on_call, CUSTOM_ADMIN_PERMISSION_ATTR, permission_name)

        return on_call  # type: ignore

    return decorator


def log_change(admin_id: int, obj: Model, change_message: str) -> None:
    LogEntry.objects.log_action(
        user_id=admin_id,
        content_type_id=ContentType.objects.get_for_model(obj).pk,
        object_id=obj.pk,
        object_repr=force_str(obj),
        action_flag=CHANGE,
        change_message=change_message,
    )


def log_change_bulk(admin_id: int, queryset: QuerySet, change_message: str) -> None:
    content_type = ContentType.objects.get_for_model(queryset.model)  # type: ignore
    log_entries = [
        LogEntry(
            user_id=admin_id,
            content_type_id=content_type.pk,
            object_id=obj.pk,
            object_repr=force_str(obj),
            action_flag=CHANGE,
            change_message=change_message,
        )
        for obj in queryset
    ]
    LogEntry.objects.bulk_create(log_entries)


def min_width(width: str = '160px') -> Callable[[Callable], Callable]:
    def wrapper(field: Callable) -> Callable:
        @functools.wraps(field)
        def inner(*args: Any, **kwargs: Any) -> Any:
            return (
                f'<span class="min-width-wrapper" style="min-width: {width};">' f'{field(*args, **kwargs)}' f'</span>'
            )

        return inner

    return wrapper


def transpose_dict(data: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    transposed_dict: dict[str, dict[str, str]] = {}
    for k, v in data.items():
        for k1, v1 in v.items():
            if k1 not in transposed_dict:
                transposed_dict[k1] = {}
            transposed_dict[k1][k] = v1
    return transposed_dict
