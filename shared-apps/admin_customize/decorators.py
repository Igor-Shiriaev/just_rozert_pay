import functools
import logging
from typing import Any, Callable, List, TypeVar, cast, TYPE_CHECKING

from django.conf import settings
from django.contrib import admin, messages
from django.db.models import Model, QuerySet
from django.http import HttpRequest
from django.utils.safestring import SafeText
from mypy_extensions import KwArg, VarArg

if TYPE_CHECKING:
    from admin_customize.admin import BaseModelAdmin

logger = logging.getLogger(__name__)


class TAdminAction:
    short_description: str
    label: str
    is_modal: bool
    show_if: Callable[[Any], bool]


class TAdminField:
    short_description: str
    boolean: bool = False
    admin_order_field: str
    inline_actions: List[str]


T_Model = TypeVar('T_Model', bound=Model)
T_ModelAdmin = TypeVar('T_ModelAdmin', bound=admin.ModelAdmin)


def cast_to_admin_action(func: 'Callable[[T_ModelAdmin, Any, T_Model], Any]') -> TAdminAction:  # type: ignore
    return cast(TAdminAction, func)


def cast_to_list_admin_action(func: 'Callable[[T_ModelAdmin, Any, QuerySet[T_Model]], Any]') -> TAdminAction:  # type: ignore
    return cast(TAdminAction, func)


def cast_to_admin_field(func: 'Callable[[T_ModelAdmin, T_Model], Any]') -> TAdminField:  # type: ignore
    return cast(TAdminField, func)


def safe_admin_method(method: 'Callable[[Any, VarArg(Any), KwArg(Any)], Any]') -> TAdminAction:  # type: ignore
    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:  # type: ignore
        try:
            return method(self, *args, **kwargs)
        except Exception as e:
            logger.exception('admin method failed', extra={'method_name': method.__name__})
            if not getattr(settings, 'SUPRESS_ADMIN_SITE_ERRORS', False):
                raise e
            if isinstance(args[0], HttpRequest):
                messages.error(args[0], 'Error occurred while executing admin action')
                return None
            return SafeText('<span style="color: red"><b>ERROR OCCURRED</b></span>')

    return cast(TAdminAction, wrapper)


def safe_admin_field(method: 'Callable[[Any, VarArg(Any), KwArg(Any)], Any]') -> TAdminField:  # type: ignore
    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:  # type: ignore
        try:
            return method(self, *args, **kwargs)
        except Exception:
            if not getattr(settings, 'SUPRESS_ADMIN_SITE_ERRORS', False):
                logger.exception('admin field method failed', extra={'method_name': method.__name__})
            return SafeText('<span style="color: red"><b>ERROR OCCURRED</b></span>')

    return cast(TAdminField, wrapper)


def field_with_request(
    field_method: Callable[['BaseModelAdmin', HttpRequest, Model], Any]
) -> Callable[['BaseModelAdmin', Model], Any]:
    """
    Decorator for field methods in ModelAdmin.
    It adds request as first argument (same as in view functions).
    Request is taken from context of the first frame with context attribute.
    """

    @functools.wraps(field_method)
    def inner(self: 'BaseModelAdmin', obj: Model) -> Any:
        import inspect

        current_frame = inspect.currentframe()
        previous_frames = inspect.getouterframes(current_frame, 2)
        for frame in previous_frames:
            if _request := getattr(frame.frame.f_locals.get('context', object()), 'request', None):
                request = _request
                break
        else:
            request = None
        return field_method(self, request, obj)

    return inner
