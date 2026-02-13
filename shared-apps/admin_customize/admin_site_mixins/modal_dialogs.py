import functools
from typing import Any, Callable, Optional

from django_htmx.http import HttpResponseClientRefresh

from admin_customize.admin_site import BetmasterAdminSite, Media
from django.contrib.admin import ModelAdmin
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from lxml import etree, html


class ModalActionsAdminSiteMixin(BetmasterAdminSite):
    USE_MODAL_ACTIONS = True

    @property
    def media(self) -> Media:
        return super().media + Media(
            css={'all': ('admin/css/_modal_dialog/modal_dialog.css',)},
            js=(
                'js/hyperscript-0.9.14.min.js',
                'admin/js/_modal_dialog/modal_dialog.js',
            ),
        )


class ModalActionsModelAdminMixin(ModelAdmin):
    """
    Mixin should be last in inheritance list
    """

    def changelist_view(self, request: HttpRequest, extra_context: dict = None) -> HttpResponse:
        response: HttpResponse = super().changelist_view(request, extra_context)
        if request.htmx:
            return self.__process_htmx_refresh_page(response)

        return response

    def change_view(
        self,
        request: HttpRequest,
        object_id: Any,
        form_url: str = "",
        extra_context: Optional[dict] = None,
    ) -> HttpResponse:
        response: HttpResponse = super().change_view(request, object_id, form_url, extra_context)
        if request.htmx:
            return self.__process_htmx_refresh_page(response)

        return response

    def __process_htmx_refresh_page(self, response: HttpResponse) -> HttpResponse:
        tree = html.fromstring(response.rendered_content)
        content = tree.xpath('//*[@id="content"]')[0]
        rendered_content = etree.tostring(content, encoding='unicode')
        return HttpResponse(rendered_content)


def modal_action(method: Callable) -> Callable:
    @functools.wraps(method)
    def func(self: Any, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.htmx:
            response = method(self, request, *args, **kwargs)
            if response is None:
                return HttpResponseClientRefresh()
            if type(response) is HttpResponse:
                response = TemplateResponse(
                    request,
                    'admin/_modal_dialog/simple_page.html',
                    {'content': response.content.decode()},
                )
            elif type(response) is TemplateResponse:
                has_errors = response.context_data.get('form').errors
                if not has_errors:
                    response.template_name = 'admin/_modal_dialog/modal_dialog_wrapper.html'
                else:
                    response.template_name = 'admin/_modal_dialog/modal_form.html'
                    response.headers['HX-Retarget'] = '.modal-content'
                response.context_data['form_post_url'] = request.path
        else:
            response = method(self, request, *args, **kwargs)

        return response

    func.is_modal = True  # type: ignore[attr-defined]
    return func
