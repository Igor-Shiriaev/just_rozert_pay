import logging
import typing as ty

logger = logging.getLogger(__name__)

P = ty.ParamSpec("P")
V = ty.TypeVar("V")


class Error(Exception):
    pass


def wrap_errors(func: ty.Callable[P, V]) -> ty.Callable[P, ty.Union[V, Error]]:
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ty.Union[V, Error]:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception("Error in wrapped function")
            return Error(f"Error: {e}")

    return wrapper
