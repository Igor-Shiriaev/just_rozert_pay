from typing import Any, Iterable, Optional, Type, Union

from admin_customize.admin.base_admin_meta import BaseAdminMeta
from admin_customize.admin.base_admin_mixins import (
    DynamicActionsAppearanceMixin,
    GroupFiltersAdminMixin,
    HiddenActionsAdmin,
    JsonPrettifyAdmin,
    OnPermissionActionAdmin,
)
from bm.django_utils.thread_local_middleware import get_thread_cache
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.admin.utils import flatten_fieldsets, unquote
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.models import Model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.text import capfirst
from django.utils.translation import gettext as _

try:
    from django.db.models import JSONField
except ImportError:
    from django.contrib.postgres.fields import JSONField  # type: ignore[no-redef,misc]  # noqa: F401


class ReverseAdminUrlMixin:
    admin_site: 'admin.AdminSite'

    def reverse_admin_url(self, name: str, args: Any = None, kwargs: Any = None) -> str:
        if ':' in name:
            raise ValueError('Name should not contain admin site name')
        return reverse(f'{self.admin_site.name}:{name}', args=args, kwargs=kwargs)


class BaseModelAdmin(
    ReverseAdminUrlMixin,
    DynamicActionsAppearanceMixin,
    HiddenActionsAdmin,
    OnPermissionActionAdmin,
    JsonPrettifyAdmin,
    GroupFiltersAdminMixin,
    metaclass=BaseAdminMeta,
):
    editable_fields: Optional[Iterable[str]] = None

    def get_change_actions(  # type: ignore
        self, request: 'HttpRequest', object_id: Optional[int], form_url: str
    ) -> Iterable[str]:
        if object_id is None:
            return []
        thread_cache = get_thread_cache()
        if thread_cache is None:
            return super().get_change_actions(request, object_id, form_url)
        if 'change_actions' in thread_cache:
            return thread_cache['change_actions']
        change_actions = super().get_change_actions(request, object_id, form_url)
        thread_cache['change_actions'] = change_actions
        return change_actions

    def get_all_field_names(
        self, request: HttpRequest, obj: Optional[Model] = None
    ) -> Iterable[str]:
        fieldsets = self.get_fieldsets(request, obj)
        fields = flatten_fieldsets(fieldsets)
        return list(filter(lambda x: x != 'id', fields))  # type: ignore

    def get_editable_fields(
        self, request: HttpRequest, obj: Optional[Model] = None
    ) -> Optional[Iterable[str]]:
        return self.editable_fields

    def get_readonly_fields(  # type: ignore[override]
        self, request: HttpRequest, obj: Optional['Model'] = None
    ) -> Iterable[str]:
        """
        It is possible to make all fields readonly by setting
        `editable_fields` to [] in the admin class.
        Or to make all fields readonly except some by passing a list of
        field names to `editable_fields` in the admin class.
        """
        editable_fields = self.get_editable_fields(request, obj)
        if editable_fields is None:
            return super().get_readonly_fields(request, obj)
        all_fields = self.get_all_field_names(request, obj)
        return [f for f in all_fields if f not in editable_fields]

    def change_view(
        self,
        request: HttpRequest,
        object_id: Optional[str],
        form_url: str = "",
        extra_context: Optional[dict] = None,
    ) -> HttpResponse:
        model_verbose_name = self.model._meta.verbose_name

        try:
            return super().change_view(request, object_id, form_url, extra_context)
        except ObjectDoesNotExist:
            self.message_user(
                request, f'{model_verbose_name} with this ID does not exist', level=messages.ERROR
            )
            return redirect(self.reverse_admin_url('index'))
        except ValueError as exc:
            self.message_user(request, f'Invalid {model_verbose_name} ID, {exc}', level=messages.ERROR)
            return redirect(self.reverse_admin_url('index'))

    def history_view(self, request, object_id, extra_context=None):
        """The 'history' admin view for this model.

        NOTE: Exact copy from ModelAdmin.history_view and modified to sort by action_time desc
        """
        from django.contrib.admin.models import LogEntry
        from django.contrib.admin.views.main import PAGE_VAR

        # First check if the user can see this history.
        model = self.model
        obj = self.get_object(request, unquote(object_id))
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, model._meta, object_id)

        if not self.has_view_or_change_permission(request, obj):
            raise PermissionDenied

        # Then get the history for this object.
        app_label = self.opts.app_label
        action_list = (
            LogEntry.objects.filter(
                object_id=unquote(object_id),
                content_type=get_content_type_for_model(model),
            )
            .select_related()
            .order_by("-action_time")
        )

        paginator = self.get_paginator(request, action_list, 100)
        page_number = request.GET.get(PAGE_VAR, 1)
        page_obj = paginator.get_page(page_number)
        page_range = paginator.get_elided_page_range(page_obj.number)

        context = {
            **self.admin_site.each_context(request),
            "title": _("Change history: %s") % obj,
            "subtitle": None,
            "action_list": page_obj,
            "page_range": page_range,
            "page_var": PAGE_VAR,
            "pagination_required": paginator.count > 100,
            "module_name": str(capfirst(self.opts.verbose_name_plural)),
            "object": obj,
            "opts": self.opts,
            "preserved_filters": self.get_preserved_filters(request),
            **(extra_context or {}),
        }

        request.current_app = self.admin_site.name

        return TemplateResponse(
            request,
            self.object_history_template
            or [
                "admin/%s/%s/object_history.html" % (app_label, self.opts.model_name),
                "admin/%s/object_history.html" % app_label,
                "admin/object_history.html",
            ],
            context,
        )


class BaseTabularInline(ReverseAdminUrlMixin, admin.TabularInline):
    pass


class BaseModelForm(forms.ModelForm):
    pass


def get_url_name_by_model(model: Union[Model, Type[Model]], action: str = 'change') -> str:
    """
    Returns the URL name for the given model and action.
    :param model: The model class or instance.
    :param action: The action to perform (default is 'change').
    :return: The URL name.
    """
    # if isinstance(model, Model):
    #     model = model.__class__
    return f'{model._meta.app_label}_{model._meta.model_name}_{action}'
