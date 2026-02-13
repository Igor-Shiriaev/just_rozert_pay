import logging
from abc import ABC, abstractmethod
from functools import wraps
from typing import Callable, ParamSpec, Type, TypeVar
from uuid import UUID

from django.db import close_old_connections

from .events import Event

logger = logging.getLogger(__name__)


class BaseProcessedEventRegistry(ABC):
    def __init__(self, event_id: UUID):
        self.event_id = event_id

    @abstractmethod
    def add(self) -> None:
        pass

    @abstractmethod
    def exists(self) -> bool:
        pass


def duplicate_event_processing_protected(
    registry_class: Type[BaseProcessedEventRegistry],
) -> Callable[[Callable[[Event], None]], Callable[[Event], None]]:
    """
    Use the decorator to avoid multiple message processing of the same message
    in case of duplicate messages in RabbitMQ.
    """

    def decorator(func: Callable[[Event], None]) -> Callable[[Event], None]:
        @wraps(func)
        def handler(event: Event) -> None:
            registry = registry_class(event.event_id)
            if registry.exists():
                logger.warning(
                    'Event is already processed, skipped',
                    extra={'event_id': event.event_id},
                )
                return None
            result = func(event)  # type: ignore
            registry.add()
            return result

        return handler

    return decorator


T = TypeVar('T')
P = ParamSpec('P')


def auto_close_old_connection(func: Callable[P, T]) -> Callable[P, T]:
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        close_old_connections()
        return func(*args, **kwargs)

    return wrapper
