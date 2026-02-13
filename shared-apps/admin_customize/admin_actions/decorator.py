from typing import Any, Callable, Optional, Protocol, TypeVar

from admin_customize.admin import BaseModelAdmin
from admin_customize.utils import humanize_string
from django.db.models import Model
from django.http import HttpRequest
from typing_extensions import ParamSpec

T_OriginalAction = Callable[[BaseModelAdmin, HttpRequest, Model], Any]

P = ParamSpec("P")
R = TypeVar("R")


class AdminActionCallable(Protocol):
    def __call__(self, model_admin: BaseModelAdmin, request: HttpRequest, obj: Model) -> Any:
        ...

    short_description: str
    label: str
    is_modal: bool
    show_if: Optional[Callable[[Any], bool]]


F_Action = TypeVar('F_Action', bound=T_OriginalAction)


def admin_action(
    verbose_name: Optional[str] = None,
    is_modal: bool = False,
    show_if: Optional[Callable[[Any], bool]] = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def admin_action_decorator(func: Callable[P, R]) -> Callable[P, R]:
        effective_name = verbose_name or humanize_string(func.__name__)
        values_map = {
            'short_description': effective_name,
            'label': effective_name,
            'is_modal': is_modal,
            'show_if': show_if,
        }
        for key, value in values_map.items():
            if value is not None:
                setattr(func, key, value)

        return func

    return admin_action_decorator


T_OriginalField = Callable[[BaseModelAdmin, Model], Any]


class AdminFieldCallable(Protocol):
    def __call__(self, model_admin: BaseModelAdmin, obj: Model) -> Any:
        ...

    short_description: str

    boolean: Optional[bool]
    admin_order_field: Optional[str]
    inline_actions: Optional[list[str]]
    show_if: Optional[Callable[[Any], bool]]


F_Field = TypeVar('F_Field', bound=T_OriginalField)


def admin_field(
    verbose_name: Optional[str] = None,
    boolean: Optional[bool] = None,
    admin_order_field: Optional[str] = None,
    inline_actions: Optional[list[str]] = None,
    show_if: Optional[Callable[[Any], bool]] = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def admin_field_decorator(
        func: Callable[P, R],
    ) -> Callable[P, R]:
        if boolean is not None and inline_actions is not None:
            raise ValueError(
                "You cannot set both 'boolean' and 'inline_actions' for the same field. "
                "Use instead `get_bool_icon` wrapper for boolean fields."
            )

        values_map = {
            'short_description': verbose_name or humanize_string(func.__name__),
            'boolean': boolean,
            'inline_actions': inline_actions,
            'admin_order_field': admin_order_field,
            'show_if': show_if,
        }

        for key, value in values_map.items():
            if value is not None:
                setattr(func, key, value)

        return func

    return admin_field_decorator
