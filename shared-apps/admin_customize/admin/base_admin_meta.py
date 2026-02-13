import functools
from typing import TYPE_CHECKING, Any, Callable, Dict, Tuple, TypeVar, Union, cast

from admin_customize.admin.content_filtration import ContentFiltrationMeta
from admin_customize.decorators import safe_admin_method
from bm.django_utils.logging import admin_log_change, admin_log_change_bulk
from bm.django_utils.thread_local_middleware import get_current_request
from bm.utils import json_dumps
from django import forms
from django.contrib import messages
from django.contrib.admin import ModelAdmin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Model, QuerySet
from django.http import HttpResponse
from django.template import loader  # type: ignore

if TYPE_CHECKING:
    from django.http import HttpRequest

R = TypeVar('R', bound=HttpResponse)
F = TypeVar('F', bound=Callable[..., Any])  # type: ignore


class AdminActionsMeta(type):
    def __new__(mcs, name: str, bases: Tuple, classdict: Dict) -> Any:  # type: ignore

        # force permission check for custom object actions
        def adminaction_permission_required(action_func: Callable) -> Callable:
            @functools.wraps(action_func)
            def on_call(self: type, request: 'HttpRequest', obj: 'Model') -> Any:  # type: ignore
                perm_name = self.get_permission_name_for_change_action(action_func.__name__)  # type: ignore
                if not request.user.has_perm(perm_name):
                    raise PermissionDenied()
                return action_func(self, request, obj)

            return on_call

        for object_action in classdict.get('change_actions', []):
            if object_action not in classdict:
                continue
            method = classdict[object_action]
            patched_method = _logged_admin_object_action_method(
                adminaction_permission_required(method)
            )
            classdict[object_action] = patched_method

        for method_name, method in classdict.items():
            if callable(method) and ('action' in method_name or 'field' in method_name):
                classdict[method_name] = safe_admin_method(method)

        # force permission check for built-in django admin actions
        def has_builtin_action_perm_method(builtin_action_method: Callable) -> Callable:
            @functools.wraps(builtin_action_method)
            def on_call(self: Any, request: 'HttpRequest') -> bool:  # type: ignore
                perm_name = '{app_label}.adminlistaction_{model_name}_{builtin_action_name}'.format(
                    app_label=self.opts.app_label,
                    model_name=self.opts.model.__name__.lower(),
                    builtin_action_name=builtin_action_method.__name__,
                )
                return request.user.has_perm(perm_name)

            return on_call

        for list_action in classdict.get('actions') or []:
            if list_action not in classdict:
                continue
            assert list_action not in ('view', 'add', 'change', 'delete')
            perm_check_method_name = 'has_%s_permission' % list_action
            # Create required 'has_<action>_permission' method which just
            # checks if user has corresponding custom permission.
            method = classdict[list_action]
            classdict[perm_check_method_name] = has_builtin_action_perm_method(method)
            classdict[list_action] = _logged_admin_action_method(method)
            # set required `allowed_permissions` attr
            classdict[list_action].allowed_permissions = (list_action,)

        return super(AdminActionsMeta, mcs).__new__(mcs, name, bases, classdict)

    @staticmethod
    def get_method_from_base_class_or_classdict(
        class_name: str, method_name: str, base_classes: Tuple, classdict: Dict[str, Callable]
    ) -> Callable:
        # try classdict first
        if method_name in classdict:
            return classdict[method_name]
        # try to find in one of bases
        for base_class in base_classes:
            method = getattr(base_class, method_name, None)
            if method is not None:
                return method
        raise AttributeError(f'{method_name} not found in class {class_name}')


def _logged_admin_action_method(action: Callable[..., R]) -> Callable[..., R]:
    @functools.wraps(action)
    def func(self: 'ModelAdmin', request: 'HttpRequest', queryset: 'QuerySet') -> R:
        response = action(self, request, queryset)
        transaction.on_commit(
            lambda: admin_log_change_bulk(
                queryset,
                change_message=_construct_change_message(
                    action_name=getattr(action, 'short_description', action.__name__),
                    extra=getattr(request, 'admin_log_extra', None),
                ),
                user_id=cast(int, request.user.id),
            )
        )
        return response

    return func


def _logged_admin_object_action_method(action: Callable[..., R]) -> Callable[..., R]:
    @functools.wraps(action)
    def func(self: 'ModelAdmin', request: 'HttpRequest', obj: 'Model') -> R:
        response = action(self, request, obj)
        has_error_message = False
        for message in request._messages._queued_messages:  # type: ignore
            if message.level == messages.ERROR:
                has_error_message = True
        if (response is None or response.status_code == 302) and not has_error_message:
            transaction.on_commit(
                lambda: admin_log_change(
                    obj,
                    change_message=_construct_change_message(
                        action_name=getattr(action, 'label', action.__name__),
                        extra=getattr(request, 'admin_log_extra', None),
                    ),
                    user_id=cast(int, request.user.id),
                )
            )
        return response

    return func


def _construct_change_message(action_name: str, extra: Union[dict, str, None] = None) -> str:
    data: dict = {'name': action_name}
    if extra:
        data['extra'] = extra
    return json_dumps(data)


def _field_with_action_link(action_name: str) -> Callable[..., Any]:  # type: ignore
    def decorator(func: F) -> F:  # type: ignore
        @functools.wraps(func)
        def wrapper(self, obj: Model, *args: Any, **kwargs: Any) -> Any:  # type: ignore
            request = get_current_request()

            user_change_actions = self.get_change_actions(request, obj.pk, '')
            if action_name not in user_change_actions:
                return func(self, obj)
            rendered_data = func(self, obj, *args, **kwargs)
            root_element = 'infield_action_link_wrapper' not in str(rendered_data)
            template = loader.get_template(
                'django_object_actions/rendered_field_wrapper_with_action_link.html'
            )
            action = getattr(self, action_name)
            return template.render(
                context={
                    'root_element': root_element,
                    'rendered_data': rendered_data,
                    'action_name': action_name,
                    'action_label': getattr(
                        action, "label", action_name.replace("_", " ").capitalize()
                    ),
                    'is_modal': getattr(action, "is_modal", False)
                    and getattr(self.admin_site, 'USE_MODAL_ACTIONS', False),
                    'tools_view_name': self.tools_view_name,
                    'obj': obj,
                },
                request=request,
            )

        return wrapper  # type: ignore

    return decorator


class HiddenActionsAdminMeta(type):
    def __new__(meta, name: str, bases: Tuple, classdict: Dict) -> Any:  # type: ignore
        import types

        hidden_actions = classdict.get('hidden_actions', [])

        for attr_name, attr in classdict.items():
            if not isinstance(attr, types.FunctionType):
                continue
            method = attr
            if hasattr(method, 'inline_actions'):
                hidden_actions.extend(method.inline_actions)  # type: ignore
                for action_name in reversed(method.inline_actions):  # type: ignore
                    method = _field_with_action_link(action_name)(method)
                classdict[attr_name] = method
        classdict['hidden_actions'] = hidden_actions
        for base_class in bases:
            if hasattr(base_class, 'hidden_actions'):
                hidden_actions.extend(base_class.hidden_actions)  # type: ignore
        return super().__new__(meta, name, bases, classdict)


# If some class would use two classes as it's bases where one is class with
# _ObjectActionsMeta as a metaclass and other is class derived from
# admin.ModelAdmin, which has metaclass forms.MediaDefiningClass,
# TypeError would be raised:
# "TypeError: metaclass conflict: the metaclass of a derived class must be a
# (non-strict) subclass of the metaclasses of all its bases".
# Thus derived metaclass ObjectActionsMeta is created manually.
class BaseAdminMeta(
    ContentFiltrationMeta,
    HiddenActionsAdminMeta,
    AdminActionsMeta,
    forms.widgets.MediaDefiningClass,
):
    pass
