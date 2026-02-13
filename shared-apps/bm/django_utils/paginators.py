import typing
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional, Dict, TypeVar, Generic, Union

from django.core.paginator import Paginator
from django.db import connection, transaction, OperationalError
from django.utils import timezone
from django.utils.functional import cached_property

if TYPE_CHECKING:
    from django.utils.timezone import datetime  # type: ignore
    from django.db.models import QuerySet, Model


class TimeLimitedPaginator(Paginator):
    @cached_property
    def count(self) -> int:  # type: ignore
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('SET LOCAL statement_timeout TO 100;')
            try:
                return super().count
            except OperationalError:
                return 999999999


class DisabledPaginator(Paginator):
    @cached_property
    def count(self) -> int:  # type: ignore
        return 999999999


class ApproximatePaginator(Paginator):
    @cached_property
    def count(self) -> int:  # type: ignore
        if self.object_list.query.where:  # type: ignore
            return super().count
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT reltuples::bigint FROM pg_class WHERE relname = %s',
                [self.object_list.model._meta.db_table],
            )
            return cursor.fetchone()[0]


T = TypeVar('T', bound='Model')


class SeekBasedPaginator(ABC, Generic[T]):
    filter_field: str

    def __init__(
        self,
        queryset: 'QuerySet[T]',
        per_page: int,
        offset_id: Optional[Union[int, float]] = None,
    ) -> None:
        self._objects_list = self._filter_by_offset_id(
            queryset,
            per_page,
            offset_id,
        )
        self.per_page = per_page

    @abstractmethod
    def _filter_by_offset_id(  # type: ignore
        self,
        queryset: 'QuerySet[T]',
        per_page: int,
        offset_id: Optional[float],
    ) -> List[T]:
        pass

    def objects_list(self) -> List[T]:
        return self._objects_list[: self.per_page]

    def has_more(self) -> bool:
        return len(self._objects_list) > self.per_page

    @abstractmethod
    def next_page_offset_id(self) -> Optional[float]:  # type: ignore
        pass

    def serialize(self) -> Dict:
        return {
            'has_more': self.has_more(),
            'next_page_offset_id': self.next_page_offset_id(),
        }

    def serialize_with_cls(self, serializer_cls: typing.Type[typing.Any]) -> dict:
        return {
            'paginator': self.serialize(),
            'items': [serializer_cls(item).data for item in self.objects_list()],
        }


class SeekByDatetimeFieldPaginator(SeekBasedPaginator, Generic[T]):
    def _timestamp_to_datetime(self, offset_timestamp: Optional[float]) -> Optional['datetime']:
        if offset_timestamp is None:
            return None
        return timezone.datetime.fromtimestamp(offset_timestamp, tz=timezone.utc)  # type: ignore

    def _filter_by_offset_id(
        self,
        queryset: 'QuerySet[T]',
        per_page: int,
        offset_id: Optional[float],
    ) -> List[T]:
        offset_datetime = self._timestamp_to_datetime(offset_id)
        if offset_datetime:
            queryset = queryset.filter(**{f'{self.filter_field}__lt': offset_datetime})
        return list(queryset[: per_page + 1])

    def next_page_offset_id(self) -> Optional[int]:
        if not self.has_more():
            return None
        return int(self.last_object_datetime.timestamp())

    @property
    def last_object_datetime(self) -> 'datetime':  # type: ignore
        last_obj = self.objects_list()[-1]

        if isinstance(last_obj, dict):
            return last_obj[self.filter_field]

        return getattr(last_obj, self.filter_field)


class SeekByCreatedPaginator(SeekByDatetimeFieldPaginator, Generic[T]):
    filter_field = 'created'


class SeekByCreatedAtPaginator(SeekByDatetimeFieldPaginator, Generic[T]):
    filter_field = 'created_at'
