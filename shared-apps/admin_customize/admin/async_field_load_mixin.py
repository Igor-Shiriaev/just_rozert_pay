import functools
import logging
from typing import TYPE_CHECKING, Any, List, Union

from bm.django_utils.thread_local_middleware import get_current_request
from django.contrib.admin import ModelAdmin
from django.http import HttpRequest, HttpResponse
from django.template import loader
from django.urls import path

from bm.common.entities import StrEnum

if TYPE_CHECKING:
    from django.db import models

logger = logging.getLogger(__name__)


class LoadOnOption(StrEnum):
    LOAD = 'load'
    REVEAL = 'revealed'


def async_load_field(
    load_on: LoadOnOption = LoadOnOption.LOAD,
):
    """Decorator to make field being loaded asynchronously."""

    def decorator(
        field_method: Any,
    ) -> Any:
        @functools.wraps(field_method)
        def wrapper(
            self: 'ModelAdmin',
            obj: 'models.Model',
            *args: Any,

            **kwargs: Any,
        ) -> Any:
            if not obj.id:
                return '-'
            request = get_current_request()
            if request.htmx:
                try:
                    return field_method(self, obj, *args, **kwargs)
                except Exception as e:
                    logger.exception('Exception in shared-apps -> async_load_field')
                    template = loader.get_template('admin/async_field_error.html')
                    return template.render(
                        {
                            'field_name': field_method.__name__,
                            'error': str(e),
                        }
                    )
            template = loader.get_template('admin/async_field_load.html')
            return template.render(
                {
                    'field_name': field_method.__name__,
                    'object_id': obj.pk,
                    'opts': self.model._meta,
                    'load_on': load_on.value,
                }
            )

        return wrapper

    return decorator


class AsyncFieldLoadMixin(ModelAdmin):
    def get_field_content(
        self, request: HttpRequest, object_id: Union[str, int], field_name: str
    ) -> HttpResponse:
        field_method = getattr(self, field_name, None)

        if not field_method:
            raise AttributeError(f'Field {field_name} not found in {self.model.__name__} admin')
        if not callable(field_method):
            raise AttributeError(
                f'Field {field_name} is not a method in {self.model.__name__} admin'
            )

        obj = self.get_object(request, object_id)
        data = field_method(obj)
        return HttpResponse(
            data,
            content_type='text/html',
        )

    def get_urls(self) -> List:
        opts = self.model._meta
        return [
            path(
                '<int:object_id>/async_field/<str:field_name>/',
                self.admin_site.admin_view(self.get_field_content),
                name='%s_%s_get_async_field' % (opts.app_label, opts.model_name),
            ),
            *super().get_urls(),
        ]
