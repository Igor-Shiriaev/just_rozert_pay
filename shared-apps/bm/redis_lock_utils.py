import contextlib
import logging
from typing import Any, Callable, Generator, cast, TypeVar
from redis import Redis     # type: ignore
from redis.exceptions import LockNotOwnedError  # type: ignore

T_Callable = TypeVar('T_Callable', bound=Callable)


logger = logging.getLogger(__name__)


@contextlib.contextmanager
def redis_lock(redis: Redis, key: str, timeout: float = 10, blocking: bool = False) -> Generator[bool, None, None]:
    lock = redis.lock(key, timeout=timeout)
    acquired = lock.acquire(blocking=blocking)
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except LockNotOwnedError as e:
                logger.warning(
                    'LockNotOwnedError occurred while releasing lock',
                    extra={
                        'key': key,
                        'error': str(e),
                    }
                )


def maybe_once_with_redis_lock(redis: Redis, key: str, timeout: float = 10) -> Callable[[T_Callable], T_Callable]:
    def decorator(callable: T_Callable) -> T_Callable:
        def wrapper(*args, **kwargs):       # type: ignore
            with redis_lock(redis, key, timeout=timeout) as acquired:
                if acquired:
                    return callable(*args, **kwargs)
                else:
                    return None
        return cast(Any, wrapper)
    return decorator
