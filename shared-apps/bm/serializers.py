import inspect

from collections import OrderedDict
from abc import ABCMeta
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Union, Any, Optional, Callable, Tuple, Generic, TypeVar

T = TypeVar('T')


class SerializerField:
    def __init__(self, serializer: Union[Callable[[Any], 'type[Serializer]'], Any] = str):     # type: ignore
        self._serializer = serializer

    def serialize(self, value: Any, context: Optional[dict]) -> Any:     # type: ignore
        if value is None:
            return None
        if self.is_class_serializer:
            assert issubclass(self._serializer, Serializer)  # type: ignore[arg-type]
            return self._serializer(value, context=context).data  # type: ignore[call-arg]
        return self._serializer(value)

    @property
    def is_class_serializer(self) -> bool:
        return inspect.isclass(self._serializer) and issubclass(self._serializer, Serializer)  # type: ignore[arg-type]

class SerializerMetaclass(ABCMeta):
    def __new__(mcs, name: str, bases: Tuple, attrs: Dict, **kwargs: Any):  # type: ignore
        serializer_fields = OrderedDict()
        for key, attr in attrs.items():
            if isinstance(attr, SerializerField):
                serializer_fields[key] = attr
        attrs['_serializer_fields'] = serializer_fields
        return super().__new__(mcs, name, bases, attrs, **kwargs)  # type: ignore


class Serializer(Generic[T], metaclass=SerializerMetaclass):
    _serializer_fields: Dict[str, SerializerField]
    context: dict

    def __init__(self, instance: Any, many: bool = False, context: Optional[dict] = None):      # type: ignore
        self.instance = instance
        self.many = many
        self.context = context or {}

    @property
    def data(self) -> Union[dict, List[dict]]:      # type: ignore
        if self.many:
            return [self.serialize(obj) for obj in self.instance]
        return self.serialize(self.instance)

    def serialize(self, obj: T) -> dict:          # type: ignore
        data = {}
        for key, field in self._serializer_fields.items():
            data[key] = field.serialize(getattr(obj, key), context=self.context)
        return data


def serialize_datetime(value: datetime) -> int:
    return int(value.timestamp())


def serialize_datetime_as_ts(value: datetime) -> int:
    return serialize_datetime(value) * 1000


def serialize_decimal(value: Decimal) -> str:
    return format(value, 'f')
