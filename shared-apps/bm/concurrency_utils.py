import functools
import json
import logging
import signal
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, Iterable, Optional, TYPE_CHECKING

from django.utils.encoding import force_str

from bm.utils import include_original
from common.redis import redis_con_low_priority

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from bm.typing_utils import T_Decorated_Function


class AlreadyLocked(Exception):
    pass


class TimeoutException(Exception):
    pass


LOCK_PREFIX = "processlock"
FALLBACK_TIMEOUT = 60 * 15  # 15 min


def lock_func_from_parallel_run(
    time: Optional[int] = None,
    suppress_already_locked_exception: bool = False,
    include_args: bool = False,
) -> Callable:
    @include_original
    def decorator(
        func: 'T_Decorated_Function',
    ) -> Callable[['T_Decorated_Function'], 'T_Decorated_Function']:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:  # type: ignore
            key = _generate_key(func, include_args, args, kwargs)
            timeout = time or FALLBACK_TIMEOUT
            if timeout <= 0:
                raise ValueError("time should be positive integer")
            try:
                with lock_in_redis(
                    timeout,
                    key,
                ):
                    with time_limit(timeout):
                        return func(*args, **kwargs)
            except AlreadyLocked:
                if suppress_already_locked_exception:
                    logger.warning("Already locked", exc_info=True)
                    return None
                raise

        return wrapper

    return decorator


@contextmanager
def lock_in_redis(time: int, key: str) -> Generator:
    lock_uuid = uuid.uuid4().hex
    with redis_con_low_priority.pipeline(transaction=True) as pipeline:
        pipeline.set(key, lock_uuid, nx=True, ex=time)
        pipeline.get(key)
        written, data = pipeline.execute()
        data = data.decode()
        if data != lock_uuid:
            raise AlreadyLocked("%s already locked", key)
    try:
        yield
    finally:
        redis_con_low_priority.delete(key)


def _generate_key(
    func: 'T_Decorated_Function',
    include_args: bool,
    args: Optional[Iterable[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
) -> str:
    key_base = func.__name__
    if include_args:
        _args = [force_str(arg) for arg in args] if args else None
        _kwargs = {k: force_str(v) for k, v in kwargs.items()} if kwargs else None
        params_str_repr = json.dumps({"args": _args, "kwargs": _kwargs})
        key_suffix: Optional[str] = str(hash(params_str_repr))
    else:
        key_suffix = None
    key_parts = [LOCK_PREFIX, key_base]
    if key_suffix:
        key_parts.append(key_suffix)
    return "_".join(key_parts)


@contextmanager
def time_limit(seconds: int) -> Generator:
    def signal_handler(*args, **kwargs) -> None:  # type: ignore
        raise TimeoutException("Timed out!")

    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)


def empty_decorator(*args, **kwargs):  # type: ignore
    def decorator(func):  # type: ignore
        return func  # type: ignore

    return decorator  # type: ignore
