from typing import (TYPE_CHECKING, Any, ClassVar, Iterable, List, Optional,
                    TypedDict, cast)

from bm.django_utils.thread_local_middleware import get_thread_cache
from django.contrib import admin, messages
from django.contrib.admin import ModelAdmin
from django.http import HttpRequest, HttpResponse
from django_object_actions import DjangoObjectActions
from pydantic import BaseModel

try:
    from django.db.models import JSONField
except ImportError:
    from django.contrib.postgres.fields import JSONField  # type: ignore[no-redef,misc]

from bm.django_utils.widgets import JSONEditorWidget

if TYPE_CHECKING:
    from django.contrib.admin import ListFilter
    from django.db.models import Model
    from django.http import HttpRequest
    from django.template.response import TemplateResponse


class HiddenActionsAdmin(DjangoObjectActions, ModelAdmin):
    hidden_actions: List[str] = []

    def get_hidden_actions(self, request: 'HttpRequest') -> List[str]:
        """
        Return a list of actions that are hidden from the user.
        """
        return self.hidden_actions

    def change_view(self, request, object_id, form_url="", extra_context=None) -> HttpResponse:  # type: ignore
        change_view_data = super().change_view(request, object_id, form_url, extra_context)
        if not hasattr(change_view_data, 'context_data'):
            return change_view_data
        context_data = change_view_data.context_data  # type: ignore
        if 'objectactions' not in context_data:
            return change_view_data
        if not self.hidden_actions:
            return change_view_data
        hidden_actions = self.get_hidden_actions(request)
        context_data['objectactions'] = [
            action_data
            for action_data in context_data['objectactions']
            if action_data['name'] not in hidden_actions
        ]
        return change_view_data


class OnPermissionActionAdmin(DjangoObjectActions, ModelAdmin):
    def get_change_actions(  # type: ignore
        self: Any, request: 'HttpRequest', object_id: Optional[int], form_url: str
    ) -> Iterable[str]:
        """Filter admin actions based on custom user permissions."""

        actions = super().get_change_actions(request, object_id, form_url)
        allowed_actions = []
        for action in list(actions):
            perm_name = self.get_permission_name_for_change_action(action)
            if request.user.has_perm(perm_name):
                allowed_actions.append(action)
        return allowed_actions

    def get_permission_name_for_change_action(self, action: str) -> str:
        return '{app_label}.adminobjectaction_{model_name}_{action_name}'.format(
            app_label=self.model._meta.app_label,
            model_name=self.opts.model.__name__.lower(),
            action_name=action,
        )


class GroupsAdditionalParams(BaseModel):
    hint: Optional[str] = None
    foldable: bool = False
    folded: bool = False


class ListFilterGroup(BaseModel):
    name: str
    filters: List[str]
    additional_params: 'GroupsAdditionalParams' = GroupsAdditionalParams()

    template: ClassVar[str] = 'admin/includes/filters_group.html'


FilterGroupParams = TypedDict(
    'FilterGroupParams', {'filters': List['ListFilter'], 'group': Optional[ListFilterGroup]}
)


class GroupFiltersAdminMixin(ModelAdmin):
    list_filter_groups: Optional[List[ListFilterGroup]] = None

    @staticmethod
    def _get_parameter_name(filter_spec: 'ListFilter') -> Optional[str]:
        if hasattr(filter_spec, 'field_path'):
            return filter_spec.field_path  # type: ignore
        if hasattr(filter_spec, 'parameter_name'):
            return filter_spec.parameter_name  # type: ignore
        return None

    def changelist_view(
        self, request: 'HttpRequest', extra_context: Optional[dict] = None
    ) -> 'TemplateResponse':
        changelist_view: 'TemplateResponse' = super().changelist_view(request, extra_context)

        return self._enrich_with_filter_groups(changelist_view)

    def _enrich_with_filter_groups(
        self, changelist_view: 'TemplateResponse'
    ) -> 'TemplateResponse':
        if not hasattr(self, 'list_filter_groups') or self.list_filter_groups is None:
            return changelist_view

        if not hasattr(changelist_view, 'context_data') or 'cl' not in (
            changelist_view.context_data or {}
        ):
            return changelist_view

        changelist_view.context_data = cast(dict, changelist_view.context_data)

        filters_specs = changelist_view.context_data['cl'].filter_specs

        filter_groups: List[FilterGroupParams] = []

        filters_in_groups = []

        for filter_group in self.list_filter_groups:
            filters = [
                filter_spec
                for filter_spec in filters_specs
                if self._get_parameter_name(filter_spec) in filter_group.filters
            ]

            filters.sort(
                key=lambda x: filter_group.filters.index(cast(str, self._get_parameter_name(x)))
            )

            filter_groups.append(FilterGroupParams(filters=filters, group=filter_group))
            filters_in_groups.extend(filter_group.filters)

        ungrouped_filters = [
            filter_spec
            for filter_spec in filters_specs
            if self._get_parameter_name(filter_spec) not in filters_in_groups
        ]

        if ungrouped_filters:
            filter_groups.append(FilterGroupParams(filters=ungrouped_filters, group=None))

        changelist_view.context_data['filter_groups'] = filter_groups
        return changelist_view


class DynamicActionsAppearanceMixin(DjangoObjectActions, ModelAdmin):
    def get_change_actions(
        self: Any,
        request: 'HttpRequest',
        object_id: Optional[Any],
        form_url: str,
    ) -> Iterable[str]:
        if isinstance(object_id, str) and '_3A' in object_id:
            object_id = object_id.replace('_3A', ':')
        actions: Iterable[str] = super().get_change_actions(request, object_id, form_url)
        obj: Optional['Model'] = self.get_object(request, object_id)

        actions_to_remove = []

        if obj is None:
            return []

        for action_name in actions:
            action_method = getattr(self, action_name)
            if action_method is None:
                continue
            try:
                if hasattr(action_method, 'show_if') and not action_method.show_if(obj):
                    actions_to_remove.append(action_name)
            except AttributeError:
                actions_to_remove.append(action_name)
        return [action for action in actions if action not in actions_to_remove]

    def get_object(self, request, object_id: Optional[Any], from_field=None):
        thread_cache = get_thread_cache()
        if thread_cache is None:
            return super().get_object(request, object_id, from_field)

        if 'admin_object' in thread_cache and isinstance(thread_cache, dict):
            if object_id in thread_cache['admin_object']:
                return thread_cache['admin_object'][object_id]
            else:
                obj = super().get_object(request, object_id, from_field)
                thread_cache['admin_object'][object_id] = obj
                return obj
        else:
            obj = super().get_object(request, object_id, from_field)
            thread_cache['admin_object'] = {object_id: obj}
            return obj


class ChangeFormWarningMixin:
    change_form_warning = None

    def render_change_form(
        self,
        request: HttpRequest,
        context: dict,
        add: bool = False,
        change: bool = False,
        form_url: str = '',
        obj=None,
    ):
        if obj and self.change_form_warning:
            messages.warning(request, self.change_form_warning)  # type: ignore[unreachable]
        return super().render_change_form(request, context, add, change, form_url, obj)  # type: ignore[misc]


class JsonPrettifyAdmin(admin.ModelAdmin):
    formfield_overrides = {
        JSONField: {'widget': JSONEditorWidget},
    }
