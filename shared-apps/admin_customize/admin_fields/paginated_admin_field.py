import logging
from typing import Any, ClassVar, Literal, Type, Union, cast

from admin_customize.admin.table_renderer import TableData
from django.contrib.admin import ModelAdmin
from django.db.models import Model, QuerySet
from django.http import HttpRequest, HttpResponse
from django.template import loader
from django.urls import path
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)


class PaginatedAdminFieldMixin(ModelAdmin):
    paginated_field_processors: dict[str, Type['PaginatedAdminTableField']] = {}

    def get_field_page(
        self, request: HttpRequest, object_id: Any, field_name: str, page_number: int
    ) -> HttpResponse:
        field_processor = self.paginated_field_processors.get(field_name)
        if field_processor is None:
            return HttpResponse(status=404)
        obj = self.get_object(request, object_id)
        if obj is None:
            return HttpResponse(status=404)

        content = field_processor(obj).get_page(page_number=page_number)

        return HttpResponse(content, content_type='text/html')

    def get_urls(self) -> list:
        opts = self.model._meta
        return [
            path(
                '<str:object_id>/paginated_field/<str:field_name>/<int:page_number>/',
                self.admin_site.admin_view(self.get_field_page),
                name='%s_%s_paginated_field' % (opts.app_label, opts.model_name),
            ),
            *super().get_urls(),
        ]


class PaginatedAdminTableField:
    PAGE_SIZE: ClassVar[int]
    FIELD_NAME: ClassVar[str]
    TEMPLATE_NAME: ClassVar[str] = 'admin/paginated_field.html'
    DATA_SOURCE_TYPE: ClassVar[Literal['list', 'queryset']] = 'list'
    MIN_PAGES_TO_COLLAPSE: ClassVar[int] = 7
    PAGES_GAP: ClassVar[str] = '...'

    data: Union[list[dict], QuerySet]

    def __init__(
        self,
        obj: 'Model',
        *,
        show_total_count: bool = False,
    ):
        self.obj = obj
        self.show_total_count = show_total_count
        if self.DATA_SOURCE_TYPE == 'list':
            self.data = self.get_source_list()
        elif self.DATA_SOURCE_TYPE == 'queryset':
            self.data = self.get_source_queryset()

        self._items_count: int = self._get_data_length()
        self._pages_count: int = self._get_pages_count()

    def get_source_list(self) -> list[dict]:
        """Get the source data for the field."""
        raise NotImplementedError('get_source_list must be implemented in subclasses')

    def get_source_queryset(self) -> QuerySet:
        """Get the source queryset for the field."""
        raise NotImplementedError('get_source_queryset must be implemented in subclasses')

    def format_data_rows(self, data: Union[list[dict], QuerySet]) -> list[dict]:
        """Format the data rows for display."""
        return cast(list[dict], data)

    @mark_safe
    def get_page(self, page_number: int) -> str:

        page_index = page_number - 1

        if self._pages_count == 1:
            data_items = self.data
        else:
            lower_bound, higher_bound = (
                page_index * self.PAGE_SIZE,
                (page_index + 1) * self.PAGE_SIZE,
            )
            data_items = self._get_data_slise(lower_bound, higher_bound)

        data_table = TableData.from_list(self.format_data_rows(data_items)).render_html(
            full_width=True, bordered=False, striped=True
        )

        context = {
            'field_name': self.FIELD_NAME,
            'data': data_items,
            'data_table': data_table,
            'page_number': page_number,
            'pages_count': self._pages_count,
            'pages': self.get_pages_bar(page_number),
            'object': self.obj,
            'obj_meta': self.obj._meta,
            'show_total_count': self.show_total_count,
            'total_count': self._items_count,
            'pages_gap': self.PAGES_GAP,
        }

        t = loader.get_template(self.TEMPLATE_NAME)
        return t.render(context)

    def get_pages_bar(self, page_num: int) -> list[Union[int, str]]:
        if self._pages_count <= self.MIN_PAGES_TO_COLLAPSE:
            return list(range(1, self._pages_count + 1))

        additional_pages = [
            p for p in [page_num - 1, page_num, page_num + 1] if 1 < p < self._pages_count
        ]

        prepend_gap = additional_pages[0] > 2
        append_gap = additional_pages[-1] < self._pages_count - 1

        pages_bar = [
            1,
            self.PAGES_GAP if prepend_gap else None,
            *additional_pages,
            self.PAGES_GAP if append_gap else None,
            self._pages_count,
        ]
        return [p for p in pages_bar if p is not None]

    def _get_pages_count(self) -> int:
        return (self._items_count // self.PAGE_SIZE) + (
            1 if self._items_count % self.PAGE_SIZE else 0
        )

    def _get_data_length(self) -> int:
        if isinstance(self.data, QuerySet):
            return self.data.count()
        return len(self.data)

    def _get_data_slise(self, lower_bound: int, higher_bound: int) -> Union[list[dict], QuerySet]:
        return self.data[lower_bound:higher_bound]

    @mark_safe
    def get_initial_page(self) -> str:
        try:
            return self.get_page(1)
        except Exception as e:
            logger.exception('Error loading paginated admin field data', exc_info=e)
            return f'Error loading data: {e}'
