import json
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, List

from django import forms
from django.conf import settings
from django.db.models import QuerySet
from django.template.response import TemplateResponse
from django.utils.safestring import SafeString
from django.contrib import messages

if TYPE_CHECKING:
    from django.db.models import Model
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class BasicAdminActionForm(forms.Form):
    PRESETS: Optional[Dict[str, Dict[str, Any]]] = None

    # action should be defined only for Admin List actions
    action: Optional[str]
    debug: bool = getattr(settings, 'DEBUG', False)
    form_template = 'admin/simple_custom_intermediate_form.html'

    fieldsets: list

    ACTION_TITLE: Optional[str] = None
    EXTENDED_HELP: Optional[SafeString] = None

    def __init__(
        self,
        request: 'HttpRequest',
        *args: Any,
        get_initial_data: bool = False,
        initial_fields: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        if initial_fields and not get_initial_data:
            raise ValueError('initial_fields can only be used with get_initial_data=True')

        self.fieldsets = []
        action_override = kwargs.pop('action', None)
        self.action = action_override or getattr(self, 'action', None)
        self.request = request

        if get_initial_data:
            initial_data = {}
            for param in request.GET:
                if initial_fields and param not in initial_fields:
                    continue
                value = request.GET.get(param, None)
                if value is None:
                    continue
                initial_data[param] = value
            kwargs.setdefault('initial', {}).update(initial_data)


        if 'do_action' in request.POST:
            super().__init__(request.POST, request.FILES, *args, **kwargs)
        else:
            super().__init__(*args, **kwargs)

    def get_admin_media(self) -> forms.Media:
        extra = '' if self.debug else '.min'
        js = [
            'vendor/jquery/jquery%s.js' % extra,
            'jquery.init.js',
            'core.js',
            'admin/RelatedObjectLookups.js',
            'actions.js',
            'urlify.js',
            'prepopulate.js',
            'vendor/xregexp/xregexp%s.js' % extra,
            'calendar.js',
            'admin/DateTimeShortcuts.js',
        ]
        if self.PRESETS:
            js.append('action_forms_presets.js')
        media = forms.Media(js=['admin/js/%s' % url for url in js])
        for field in self.fields.values():
            media += field.widget.media
        return media

    def get_additional_context(self) -> Dict[str, Any]:
        return {}

    def get_presets_context(self) -> List[Dict[str, Any]]:
        if not self.PRESETS:
            return []

        result = []
        for label, field_values in self.PRESETS.items():
            prefixed_data = {}
            for field_name, value in field_values.items():
                full_name = self.add_prefix(field_name)
                prefixed_data[full_name] = value

            result.append({
                'label': label,
                'data_json': json.dumps(prefixed_data, ensure_ascii=False)
            })
        return result

    def make_context(
        self,
        *,
        model: Type['Model'],
        no_obj: bool = False,
        obj: Optional['Model'] = None,
        queryset: Optional['QuerySet'] = None,
    ) -> Dict[str, Any]:
        if not no_obj and obj is None and queryset is None:
            raise ValueError('Either obj or queryset should be provided')
        context = {
            'opts': model._meta,
            'form': self,
            'media': self.get_admin_media(),
            'action_title': self.get_action_title(),
            **self.get_additional_context(),
        }
        if self.EXTENDED_HELP is not None:
            context['extended_help'] = self.EXTENDED_HELP
        if obj is not None:
            context.update({'obj': obj})  # type: ignore
        elif queryset is not None:
            context.update({'queryset': queryset})  # type: ignore
        return context

    def render_form_page(
        self,
        model: Type['Model'],
        no_obj: bool = False,
        obj: Optional['Model'] = None,
        queryset: Optional['QuerySet'] = None,
    ) -> TemplateResponse:
        context = self.make_context(model=model, obj=obj, queryset=queryset, no_obj=no_obj)
        return TemplateResponse(self.request, self.form_template, context)

    @property
    def has_fieldsets(self) -> bool:
        return bool(self.fieldsets)

    def get_action_title(self) -> Optional[str]:
        return self.ACTION_TITLE

    def process(self) -> None:
        pass

    def process_for_queryset(self, queryset: 'QuerySet') -> None:
        pass

    def message_user(self, message: str, level: int = messages.INFO) -> None:
        if level not in set(messages.DEFAULT_TAGS.keys()):
            raise ValueError(f'Invalid message level: {level}')
        messages.add_message(self.request, level, message)

