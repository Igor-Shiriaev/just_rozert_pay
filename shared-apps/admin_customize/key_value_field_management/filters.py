from typing import Collection, Iterable, Tuple, Type

from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.db.models import Q, QuerySet
from django.http import HttpRequest


class KeyValueFilter(admin.SimpleListFilter):
    model_field_name: str
    options: Collection[str] = ()

    SET = 'set'
    NOT_SET = 'not_set'

    def lookups(self, request: HttpRequest, model_admin: Type[ModelAdmin]) -> Iterable[Tuple[str, str]]:
        return ((self.NOT_SET, 'Not set'), (self.SET, 'Set'), *[(n, n) for n in self.options])

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        value = self.value()
        if value is None:
            return queryset
        lookup_obj = f'{self.model_field_name}__{self.parameter_name}'
        if value == self.NOT_SET:
            filtering_params = Q(**{f'{lookup_obj}__isnull': True}) | Q(**{f'{lookup_obj}__exact': {}})
            return queryset.filter(filtering_params)
        if value == self.SET:
            return queryset.filter(**{f'{lookup_obj}__isnull': False}).exclude(**{f'{lookup_obj}__exact': {}})
        if value in self.options:
            filtering_params = {f'{lookup_obj}__has_key': self.value()}
            return queryset.filter(**filtering_params)
        return queryset
