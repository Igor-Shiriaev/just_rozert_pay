from functools import wraps
from typing import Any, Callable, Type, TypeVar, cast

from django.db import models

_F = TypeVar('_F', bound=models.Field)
_M = TypeVar('_M', bound=Callable[..., tuple])
_MC = TypeVar('_MC')


def patch_to_ignore_attr(field: _F, attr_name: str) -> _F:
    """
    Removes an attribute from "deconstruct" method`s return value
    (as it is used in migrations to make diff).
    """

    if not isinstance(field, models.Field):
        raise TypeError('Expected a field')

    def deconstruction_clearing(method: _M) -> _M:
        @wraps(method)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            name, path, args, kwargs = method(*args, **kwargs)
            kwargs.pop(attr_name, None)
            return name, path, args, kwargs

        return cast(_M, wrapper)

    if hasattr(field, 'deconstruct'):
        field.deconstruct = deconstruction_clearing(field.deconstruct)  # type: ignore
    return field


def ignore_metadata_in_migrations(model_class: Type[_MC]) -> Type[_MC]:
    if not issubclass(model_class, models.Model):
        raise TypeError('Expected a model class')

    for field_name in [f.name for f in model_class._meta.fields]:
        field = model_class._meta.get_field(field_name)
        patch_to_ignore_attr(field, 'choices')
        patch_to_ignore_attr(field, 'help_text')
    return cast(Type[_MC], model_class)
