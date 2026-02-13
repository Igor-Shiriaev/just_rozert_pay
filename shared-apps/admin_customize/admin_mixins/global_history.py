import functools
from typing import Any, Callable, Optional

from admin_customize.admin import BaseModelAdmin
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import Model, TextField
from django.db.models.functions import Cast
from django.http import HttpRequest
from django.template.response import TemplateResponse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from mypy_extensions import KwArg, VarArg


class GlobalHistoryMixin(BaseModelAdmin):
    global_history_template = None

    def get_readonly_fields(self, request: HttpRequest, obj: 'Model' = None) -> list[str]:
        readonly_fields = super(GlobalHistoryMixin, self).get_readonly_fields(request, obj)
        return [*readonly_fields, 'history_page_link', 'global_history_link']

    def get_urls(self) -> list[Any]:
        from django.urls import path

        def wrap(
            view: Callable[[Any, Optional[dict[Any, Any]]], Any]
        ) -> Callable[[VarArg(Any), KwArg(Any)], Any]:
            def wrapper(*args: Any, **kwargs: Any):  # type: ignore
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self  # type: ignore
            return functools.update_wrapper(wrapper, view)

        info = self.model._meta.app_label, self.model._meta.model_name
        urls = [
            path(
                'global_history/',
                wrap(self.global_history_view),
                name='%s_%s_global_history' % info,
            ),
            *super().get_urls(),
        ]

        return urls

    def global_history_view(
        self, request: HttpRequest, extra_context: dict = None
    ) -> TemplateResponse:
        from django.contrib.admin.models import LogEntry
        from django.contrib.admin.views.main import PAGE_VAR

        model = self.model
        changelist_view = self.changelist_view(request, extra_context)
        queryset = changelist_view.context_data['cl'].queryset

        if not self.has_view_permission(request):
            raise PermissionDenied

        app_label = self.opts.app_label
        action_list = (
            LogEntry.objects.filter(
                object_id__in=queryset.annotate(
                    str_id=Cast('id', output_field=TextField())
                ).values_list('str_id', flat=True),
                content_type=ContentType.objects.get_for_model(model),
            )
            .select_related()
            .order_by('-action_time')
        )

        paginator = self.get_paginator(request, action_list, 100)
        page_number = request.GET.get(PAGE_VAR, 1)
        page_obj = paginator.get_page(page_number)
        page_range = paginator.get_elided_page_range(page_obj.number)

        context = {
            **self.admin_site.each_context(request),
            'title': 'Change history: %s' % self.opts.verbose_name_plural,
            'subtitle': None,
            'action_list': page_obj,
            'page_range': page_range,
            'page_var': PAGE_VAR,
            'pagination_required': paginator.count > 100,
            'module_name': str(capfirst(self.opts.verbose_name_plural)),
            'opts': self.opts,
            'preserved_filters': self.get_preserved_filters(request),
            **(extra_context or {}),
        }

        request.current_app = self.admin_site.name

        return TemplateResponse(
            request,
            self.global_history_template
            or [
                "admin/%s/%s/global_history.html" % (app_label, self.opts.model_name),
                "admin/%s/global_history.html" % app_label,
                "admin/global_history.html",
            ],
            context,
        )

    @mark_safe
    def global_history_link(self, *args: Any, **kwargs: Any) -> str:
        url = self.reverse_admin_url(
            f'%s_%s_global_history' % (self.opts.app_label, self.opts.model_name)
        )
        return format_html('<a href="{}">Global history</a>', url)

    global_history_link.short_description = 'Global history'

    @mark_safe
    def history_page_link(self, obj: Model) -> str:
        url = self.reverse_admin_url(
            f'%s_%s_history' % (self.opts.app_label, self.opts.model_name),
            args=(obj.pk,),
        )
        return format_html('<a href="{}">History</a>', url)

    history_page_link.short_description = 'History'
