import json
import logging
from datetime import datetime, timezone, timedelta
from functools import update_wrapper
from typing import TYPE_CHECKING, Any, Optional, Union
from unittest.mock import Mock
from uuid import uuid4

from bm.entities.messaging import UserContactType
from django import forms
from django.contrib import admin
from django.contrib.admin.options import IS_POPUP_VAR
from django.http import HttpResponse
from django.shortcuts import render
from django.template import Context, Template, loader, TemplateSyntaxError  # type: ignore
from django.template.backends.django import Template as DjangoTemplate
from django.urls import reverse
from django.utils.html import escape
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from pydantic import BaseModel

if TYPE_CHECKING:
    from django.db.models import Model
    from django.http import HttpRequest

logger = logging.getLogger(__name__)


class PreviewParam(BaseModel):
    field_name: str
    field_label: Optional[str]
    choices: list[tuple[str, str]]
    default: Optional[str] = None


class PreviewParamsForm(forms.Form):
    def __init__(self, *args: Any, preview_params: list[PreviewParam], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for preview_param in preview_params:
            self.fields[preview_param.field_name] = forms.ChoiceField(
                choices=preview_param.choices,
                label=preview_param.field_label,
                required=False,
                initial=preview_param.default or preview_param.choices[0][0],
            )

    def clean(self) -> dict:
        cleaned_data = super().clean()
        for k, v in cleaned_data.items():
            if not v:
                cleaned_data[k] = self.fields[k].initial
        return cleaned_data


class HTMLPreviewMixin(admin.ModelAdmin):
    _DEFAULT_IFRAME_WIDTH = "100%"
    _DEFAULT_IFRAME_HEIGHT = "600px"

    SUPPRESS_RENDERING_ERRORS: bool = False

    AUTO_IFRAME_HEIGHT = "auto"

    def _render_template(
        self,
        template: Union[str, DjangoTemplate],
        context: dict,
    ) -> str:
        context_obj = Context(context)
        if isinstance(template, DjangoTemplate):
            template_obj = template
            return template_obj.render(context_obj)
        else:
            template_obj = Template(template)
            return template_obj.render(context_obj)

    @mark_safe
    def render_preview(  # type: ignore
        self,
        obj: "Model",
        field_name: str,
        prefix: str,
        width: str = None,
        height: str = None,
        max_height: str = None,
        min_height: str = None,
        max_width: str = None,
        min_width: str = None,
    ) -> Optional[str]:
        data = self.get_preview_template(obj, field_name, prefix)
        context = self.get_preview_context(obj, field_name, prefix)
        if not data:
            return None

        try:
            prepared_template = self._render_template(data, context)
        except TemplateSyntaxError as e:
            prepared_template = f"Error occurred: {str(e)}"
        except Exception as e:
            if not self.SUPPRESS_RENDERING_ERRORS:
                logger.exception('Exception in shared-apps -> render_preview')
            return f"Error occurred: {str(e)}"

        t = loader.get_template("admin/html_preview/html_preview.html")
        return t.render(
            {
                'opts': self.model._meta,
                'object': obj,
                'field_name': field_name,
                'template': prepared_template,
                'template_raw': data,
                'iframe_width': width or self._DEFAULT_IFRAME_WIDTH,
                'iframe_height': height or self._DEFAULT_IFRAME_HEIGHT,
                'iframe_autoheight': height == self.AUTO_IFRAME_HEIGHT,
                'min_height': min_height,
                'max_height': max_height,
                'min_width': min_width,
                'max_width': max_width,
                'id_prefix': f'{prefix}-' if prefix is not None else '',
            }
        )

    def get_urls(self):  # type: ignore
        from django.urls import path

        def wrap(view):  # type: ignore
            def wrapper(*args, **kwargs):  # type: ignore
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self  # type: ignore
            return update_wrapper(wrapper, view)

        info = self.model._meta.app_label, self.model._meta.model_name

        urls = super().get_urls()
        urls.extend(
            [
                path(
                    "<path:object_id>/html_preview/<path:field_name>",
                    wrap(self.preview_view),
                    name="%s_%s_preview" % info,
                ),
                path(
                    "<path:object_id>/html_preview_raw/<path:field_name>",
                    wrap(self.render_preview_iframe),
                    name="%s_%s_preview_raw" % info,
                ),
            ]
        )
        return urls

    def render_preview_iframe(
        self, request: "HttpRequest", object_id: Any, field_name: str
    ) -> HttpResponse:
        if not request.headers.get('HX-Request'):
            return HttpResponse(status=404)

        try:
            obj = self.model.objects.get(id=object_id)

            template = self.get_preview_template(obj, field_name)
            context = self.get_preview_context(obj, field_name)

            prefix = f'{obj._meta.model_name}-{obj.id}-{field_name}'
            prefix_str = f"{prefix}-" if prefix else ""

            json_data = request.POST.get(f'{prefix_str}json-input', '{}') or '{}'

            try:
                json_context = json.loads(json_data)
                if isinstance(json_context, dict):
                    context.update(json_context)
            except json.JSONDecodeError:
                return HttpResponse(
                    f'<iframe id="{prefix_str}preview" class="html-preview" '
                    f'srcdoc="<div style=\'color:red\'>Invalid JSON data</div>">'
                )

            try:
                rendered_template = self._render_template(template=template, context=context)

                return HttpResponse(
                    f'<iframe id="{prefix_str}preview" class="html-preview" '
                    f'srcdoc="{escape(rendered_template)}" '
                    f'onload="iframe_loaded(this)"></iframe>'
                )
            except Exception as e:
                return HttpResponse(
                    f'<iframe id="{prefix_str}preview" class="html-preview" '
                    f'srcdoc="<div style=\'color:red\'>Error: {str(e)}</div>" '
                    f'onload="iframe_loaded(this)"></iframe>'
                )

        except Exception as e:
            return HttpResponse(
                f'<iframe class="html-preview" srcdoc="<div style=\'color:red\'>Server error: {str(e)}</div>">'
            )

    def make_preview_links(
        self, obj: "Model", field_names: list[str]
    ) -> Optional[list[tuple[str, str]]]:
        if not obj:
            return None
        links = []
        info = self.model._meta.app_label, self.model._meta.model_name
        for field_name in field_names:
            url = reverse(
                "admin:%s_%s_preview" % info,
                kwargs={"object_id": obj.id, "field_name": field_name},
            )
            query = urlencode({IS_POPUP_VAR: 1})
            links.append((f"{url}?{query}", field_name))
        return links

    @mark_safe
    def preview_with_params(self, obj: "Model", *field_names: str) -> str:
        links = self.make_preview_links(obj, list(field_names))
        t = loader.get_template("admin/html_preview/preview_links.html")
        return t.render({"links": links})

    def get_preview_context(
        self, obj: "Model", field_name: str, prefix: Optional[str] = None
    ) -> dict:
        return {}

    def get_fake_user_context(self) -> Mock:
        fake_user = Mock(
            first_name='Test User',
            nickname='testuser',
            uuid=uuid4(),
            country='DE',
            language='en',
            dobyy='1990',
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
            date=datetime.now(tz=timezone.utc).strftime('%d.%m.%Y'),
            currency='USD',
            dob_weekday=datetime.now(tz=timezone.utc).weekday(),
            unsubscribe_url='https://example.com/unsubscribe',
            last_name=None,
            last_login=(datetime.now(tz=timezone.utc) - timedelta(days=1)),
            account_id=None,
        )
        def _get_contact_by_type(contact_type: UserContactType) -> Optional[Mock] :
            if contact_type == UserContactType.EMAIL:
                return Mock(contact='example@example.com')
            elif contact_type == UserContactType.PHONE:
                return Mock(contact='+1234567890')
            elif contact_type == UserContactType.WHATSAPP:
                return Mock(contact='+1234567890')
            return None  # type: ignore

        fake_user.get_contact_by_type = _get_contact_by_type
        return fake_user



    def get_preview_template(
        self, obj: "Model", field_name: str, prefix: Optional[str] = None
    ) -> Optional[Union[str, DjangoTemplate]]:
        raise NotImplementedError()

    def get_preview_params(self, obj: "Model", prefix: Optional[str] = None) -> list[PreviewParam]:
        raise NotImplementedError()

    def preview_view(
        self, request: "HttpRequest", object_id: Any, field_name: str
    ) -> "HttpResponse":
        obj = self.model.objects.get(id=object_id)
        template = self.get_preview_template(obj, field_name)
        preview_params = self.get_preview_params(obj, field_name)
        context = self.get_preview_context(obj, field_name)

        params = {k: v for k, v in request.GET.items() if k != IS_POPUP_VAR}
        form = PreviewParamsForm(params or None, preview_params=preview_params)
        if form.is_valid():
            context.update(form.cleaned_data)

        try:
            prerendered_template: Optional[str] = self._render_template(
                template=template, context=context
            )
            error: Optional[str] = None
        except Exception as e:
            prerendered_template = None
            error = str(e)

        return render(
            request,
            "admin/html_preview/preview_with_params.html",
            {
                "template": prerendered_template,
                "error": error,
                "preview_params": preview_params,
                "form": form,
                "object": obj,
                "opts": self.model._meta,
                "is_popup": request.GET.get(IS_POPUP_VAR, False),
            },
        )
