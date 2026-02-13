import functools
import time
from functools import wraps
from typing import Callable, Optional, TypeVar, Union

T = TypeVar('T', bound=Callable)


def _is_cache_expired(last_update_ts: float, ttl_seconds: Union[float, int]) -> bool:
    return last_update_ts + ttl_seconds < time.time()


def lru_cache(
    max_size: int = 1000,
    ttl_seconds: Optional[Union[float, int]] = None,
    ignore_in_unittests: bool = False,
) -> Callable[[T], T]:
    last_update = time.time()

    def deco(func):     # type: ignore
        cached_func = functools.lru_cache(maxsize=max_size)(func)

        @wraps(func)
        def inner(*a, **k):     # type: ignore
            nonlocal last_update

            if ignore_in_unittests:
                from django.conf import settings
                if getattr(settings, 'IS_UNITTESTS', False):
                    return func(*a, **k)

            if ttl_seconds:
                if _is_cache_expired(last_update_ts=last_update, ttl_seconds=ttl_seconds):
                    cached_func.cache_clear()
                    last_update = time.time()

            return cached_func(*a, **k)

        inner.cache_clear = cached_func.cache_clear     # type: ignore
        inner.cache_info = cached_func.cache_info       # type: ignore
        return inner

    return deco

