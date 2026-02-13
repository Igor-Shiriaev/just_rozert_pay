from typing import Any, ClassVar, Type, cast

from bm.django_utils.paginators import DisabledPaginator
from django.core.paginator import Page
from django.db.models import QuerySet


class PartitionModelPage(Page):
    LIMIT_TO_TRIGGER_CORRECT_PLAN = 3000

    def __init__(self, *args: Any, trigger_limit: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.LIMIT_TO_TRIGGER_CORRECT_PLAN = trigger_limit
        if isinstance(self.object_list, QuerySet):  # type: ignore
            self.object_list = cast(QuerySet, self.object_list)  # type: ignore
            qs_low_mark = self.object_list.query.low_mark
            qs_high_mark = self.object_list.query.high_mark

            if qs_high_mark - qs_low_mark < self.LIMIT_TO_TRIGGER_CORRECT_PLAN:
                patched_qs_high_mark = qs_low_mark + self.LIMIT_TO_TRIGGER_CORRECT_PLAN

                extended_query = self.object_list
                extended_query.query.high_mark = patched_qs_high_mark

                if isinstance(self.object_list.query.select_related, dict):
                    base_qs = self.object_list.model.objects.select_related(
                        *list(self.object_list.query.select_related.keys())
                    )
                else:
                    base_qs = self.object_list.model.objects.filter()

                final_query = base_qs.filter(
                    id__in=extended_query.values_list('id', flat=True)
                ).order_by(*self.object_list.query.order_by)[: qs_high_mark - qs_low_mark]

                self.object_list = final_query


class PartitionModelPaginator(DisabledPaginator):
    page_class: ClassVar[Type[PartitionModelPage]] = PartitionModelPage
    limit_to_trigger_correct_plan: ClassVar[int]

    def _get_page(self, *args: Any, **kwargs: Any) -> Page:
        return self.page_class(*args, trigger_limit=self.limit_to_trigger_correct_plan, **kwargs)

    @classmethod
    def make_paginator(cls, limit: int) -> Type['PartitionModelPaginator']:
        return cast(
            Type['PartitionModelPaginator'],
            type('PartitionModelPaginator', (cls,), {'limit_to_trigger_correct_plan': limit}),
        )
