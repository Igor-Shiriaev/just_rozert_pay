from typing import Optional, Type, Union, Callable, Any, TypeVar, cast

from pydantic import BaseModel

from .common.entities import StrEnum
from .utils import instance_as_data

T = TypeVar('T')

MISSING = object()


def extra_property(
    name: str,
    default: T = MISSING,       # type: ignore
    default_factory: Callable[[], T] = MISSING,   # type: ignore
    serializer: Optional[Callable[[T], Any]] = None,
    deserializer: Optional[Callable[[Any], T]] = None,
    read_only: bool = False
) -> T:
    def fget(self: Any) -> Any:
        nonlocal default
        if default_factory is not MISSING:
            default = default_factory()
        if default is not MISSING:
            if not self.extra:
                return default
            if name not in self.extra:
                return default
        if deserializer is not None:
            value = self.extra[name]
            if value is None:
                return value
            return deserializer(self.extra[name])
        return self.extra[name]

    if read_only:
        return property(fget)   # type: ignore

    def fset(self: Any, value: Any) -> None:
        if serializer is not None and value is not None:
            value = serializer(value)
        self.extra[name] = value

    return property(fget, fset)     # type: ignore


T_pydantic_extra_property = TypeVar('T_pydantic_extra_property', bound=BaseModel)


def pydantic_extra_property(
    name: str,
    model: Type[T_pydantic_extra_property],
    default: Union[T_pydantic_extra_property, list] = cast(Any, MISSING),
    default_factory: Callable[[], T_pydantic_extra_property] = MISSING,     # type: ignore
) -> Union[T_pydantic_extra_property, list[T_pydantic_extra_property]]:

    def serialize(v):       # type: ignore
        if isinstance(v, list):
            return [
                instance_as_data(item) for item in v
            ]
        return instance_as_data(v)

    def deserialize(v):     # type: ignore
        if isinstance(v, list):
            return [
                model(**item)
                for item in v
            ]
        return model(**v)

    return extra_property(
        name=name,
        serializer=serialize,
        deserializer=deserialize,
        default=default,
        default_factory=default_factory,
    )


T_enum_extra_property = TypeVar('T_enum_extra_property', bound=StrEnum)


def enum_extra_property(
    name: str,
    enum: Type[T_enum_extra_property],
    default: T_enum_extra_property = cast(Any, MISSING),
) -> T_enum_extra_property:

    def serialize(v: T_enum_extra_property) -> str:
        return cast(str, v.value)

    def deserialize(v: str) -> T_enum_extra_property:
        return enum(v)

    return extra_property(
        name=name,
        serializer=serialize,
        deserializer=deserialize,
        default=default,
    )
