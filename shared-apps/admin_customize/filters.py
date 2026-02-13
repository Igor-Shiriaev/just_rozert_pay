from typing import (
    TYPE_CHECKING, Dict, Iterable, Iterator, NoReturn, Union,
    cast,
)

from django.contrib.admin import ModelAdmin
from django.contrib.admin.filters import BooleanFieldListFilter, ListFilter
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model

if TYPE_CHECKING:
    from django.contrib.admin import ModelAdmin
    from django.contrib.admin.views.main import ChangeList
    from django.http import HttpRequest

from typing import Any, Generator, List, Mapping, Optional, Tuple, Type

from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.db.models import QuerySet
from django.http import HttpRequest


class InputFilter(admin.SimpleListFilter):
    template = 'admin/input_filter.html'

    def has_output(self) -> bool:
        return True

    def lookups(  # type: ignore
        self, request: HttpRequest, model_admin: Type[admin.ModelAdmin]
    ) -> Optional[List[Tuple[Any, str]]]:
        return None

    def choices(self, changelist: ChangeList) -> Generator[Mapping[str, Any], None, None]:  # type: ignore
        # Grab only the "all" option
        all_choice = next(super().choices(changelist))  # type: ignore
        all_choice['query_parts'] = (
            (k, v) for k, v in changelist.get_filters_params().items() if k != self.parameter_name
        )
        yield all_choice

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> Optional[QuerySet]:
        raise NotImplementedError


class BooleanDropdownFilter(BooleanFieldListFilter):
    template = 'django_admin_listfilter_dropdown/dropdown_filter.html'


class PresetsFilter(ListFilter):
    parameter_name: Optional[str] = None

    def __init__(
        self,
        request: HttpRequest,
        params: Dict[str, str],
        model: Type[Model],
        model_admin: ModelAdmin,
    ) -> None:
        super().__init__(request, params, model, model_admin)  # type: ignore
        if self.parameter_name is None:
            raise ImproperlyConfigured("The filter '%s' does not specify a 'parameter_name'." % self.__class__.__name__)
        self.used_parameters = None
        if self.parameter_name in params:
            self.used_parameters = ','.join(set(params[self.parameter_name].split(',')))
        self.current_params = params.copy()
        self.lookup_choices = list(self.lookups(request, model_admin))

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> Union[Iterable[Tuple[Any, str]], NoReturn]:
        raise NotImplementedError(
            'The MultipleChoiceFilter.lookups() method must be overridden to '
            'return a list of tuples (value, verbose value).'
        )

    def value(self) -> Optional[str]:
        return self.used_parameters

    def has_output(self) -> bool:
        return True

    def choices(self, changelist: Any) -> Iterator[Dict[str, Any]]:
        for lookup, title in self.lookup_choices:
            query = ','.join(set(self.get_preset_by_value(lookup)))
            yield {
                'query_string': changelist.get_query_string({self.parameter_name: query}),  # type: ignore
                'display': title,
                'selected': self.value() == query,
            }

    def get_preset_by_value(self, value: str) -> List[str]:
        raise NotImplementedError('You must implement get_preset_by_value() method')

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> Optional[QuerySet]:
        return None

    def expected_parameters(self) -> List[str]:
        return []


class MultipleChoiceFilter(ListFilter):
    template = 'admin/multiple_choices_filter.html'

    parameter_name: Optional[str] = None

    def __init__(
        self,
        request: HttpRequest,
        params: Dict[str, str],
        model: Type[Model],
        model_admin: ModelAdmin,
    ) -> None:
        super().__init__(request, params, model, model_admin)  # type: ignore
        if self.parameter_name is None:
            raise ImproperlyConfigured("The filter '%s' does not specify a 'parameter_name'." % self.__class__.__name__)
        if used_parameters := params.get(self.parameter_name):
            self.used_parameters[self.parameter_name] = used_parameters.split(',')
        self.lookup_choices = list(self.lookups(request, model_admin))

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> Union[Iterable[Tuple[Any, str]], NoReturn]:
        raise NotImplementedError(
            'The MultipleChoiceFilter.lookups() method must be overridden to '
            'return a list of tuples (value, verbose value).'
        )

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> Optional[QuerySet]:
        raise NotImplementedError(
            'The MultipleChoiceFilter.queryset() method must be overridden to ' 'return a filtered queryset.'
        )

    def expected_parameters(self) -> List[str]:
        return [cast(str, self.parameter_name)]

    def has_output(self) -> bool:
        return True

    def value(self) -> List[str]:
        return self.used_parameters.get(self.parameter_name, [])

    def choices(self, changelist: Any) -> Iterator[Dict[str, Any]]:
        values = self.value()
        for lookup, title in self.lookup_choices:
            yield {
                'lookup': lookup,
                'display': title,
                'selected': lookup in values,
            }
