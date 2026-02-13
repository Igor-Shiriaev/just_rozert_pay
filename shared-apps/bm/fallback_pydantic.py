from typing import Any, Callable, Optional

from pydantic import BaseModel, Field


def FallbackField(
    *args: Any,
    fallback_value: Optional[Any] = None,
    fallback_factory: Optional[Callable[[], Any]] = None,
    **kwargs: Any,
) -> Any:
    """
    Creates a Pydantic Field with a fallback value or factory.
    If there is no value for annotated field, the fallback value or factory will be used.

    :param args: Positional arguments to pass to the Field.
    :param fallback_value: A static value to use as a fallback.
    :param fallback_factory: A callable that returns a fallback value.
    :param kwargs: Additional keyword arguments to pass to the Field.
    :raises ValueError: If both fallback_value and fallback_factory are set, or if neither is set.
    :return: FieldInfo: A Pydantic Field with the specified fallback behavior.
    """

    if fallback_value is not None and fallback_factory is not None:
        raise ValueError('Only one of fallback_value or fallback_factory can be set')
    if fallback_value is None and fallback_factory is None:
        raise ValueError('One of fallback_value or fallback_factory must be set')
    return Field(*args, **kwargs, fallback_value=fallback_value, fallback_factory=fallback_factory)  # type: ignore[pydantic-field]


class FallbackCompatibleModel(BaseModel):
    @classmethod
    def parse_obj(cls, obj: Any, use_fallback: bool = False) -> 'BaseModel':  # type: ignore[override]
        if not use_fallback:
            return super().parse_obj(obj)
        for field_name, field in cls.__fields__.items():
            if field_name not in obj:
                if (field_fallback := field.field_info.extra.get('fallback_value')) is not None:
                    obj[field_name] = field_fallback
                elif (
                    field_fallback_factory := field.field_info.extra.get('fallback_factory')
                ) is not None:
                    obj[field_name] = field_fallback_factory()
        return super().parse_obj(obj)
