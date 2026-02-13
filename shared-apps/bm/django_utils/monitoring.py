import contextlib
import contextvars
import functools
import logging
import os
import threading
import time
import traceback
from typing import (
    Type,
    Callable,
    Any,
    Iterator,
    Generator,
)


def _http_allowed_duration_sec_per_request(self: Any, request: Any, **kwargs: Any) -> float:
    # hostname = urlparse(request.url).hostname

    # if hostname in ['messaging', 'promotion']:
    #     # All internal requests must be fast
    #     return 1

    # If ALLOW_SLOW_DURATIONS envvar not set, allow max 2 sec requests.
    # Some pods, i.e. payment-deposit/payout workers may want to override this setting.
    return Config.HTTP_DEFAULT_DURATION if not os.environ.get('ALLOW_SLOW_DURATIONS') else 20


def _postgres_allowed_duration_sec_per_query(self, sql, params, many, executor) -> float:       # type: ignore
    return Config.QUERY_EXECUTION_THRESHOLD_SECONDS


def _mongo_allowed_duration_sec_per_query(*args: Any, **kwargs: Any) -> float:
    if kwargs.get('spec', {}).get('hello', None):
        return 10000
    return Config.QUERY_EXECUTION_THRESHOLD_SECONDS


class Config:
    QUERY_EXECUTION_THRESHOLD_SECONDS = int(os.environ.get('QUERY_EXECUTION_THRESHOLD_SECONDS', 1))
    HTTP_DEFAULT_DURATION = 2

    # NOTE: This is how you can override allowed duration thresholds for certain context. I.e. we want
    # set postgres select queries to `sometable` threshold to 10:
    #
    # >>> def custom_postgres_allowed_duration_sec_per_query(self, sql, *args, **kwargs):
    # >>>     if 'select' in sql.lower() and 'sometable' in sql:
    # >>>         return 10
    # >>>     return _postgres_allowed_duration_sec_per_query(self, sql, *args, **kwargs)
    # >>> monitoring.Config.POSTGRES_ALLOWED_DURATION_FUNC = staticmethod(
    # >>>   custom_postgres_allowed_duration_sec_per_query)

    HTTP_ALLOWED_DURATION_FUNC = staticmethod(_http_allowed_duration_sec_per_request)
    POSTGRES_ALLOWED_DURATION_FUNC = staticmethod(_postgres_allowed_duration_sec_per_query)
    MONGO_ALLOWED_DURATION_FUNC = staticmethod(_mongo_allowed_duration_sec_per_query)


logger = logging.getLogger(__name__)

local_context: contextvars.ContextVar[dict] = contextvars.ContextVar('monitoring_local_context', default={})


IS_PATCHED = False


def patch() -> None:
    global IS_PATCHED
    if IS_PATCHED:
        return

    patch_django()
    patch_mongo()
    patch_requests()

    IS_PATCHED = True


POSTGRES = 'postgres'
MONGO = 'mongo'
HTTP = 'http'

ALL_KEYS = [POSTGRES, MONGO, HTTP]


@contextlib.contextmanager
def notify_if_query_total_time_exceeds_threshold(postgres_threshold: float = None,
                                                 mongo_threshold: float = None,
                                                 http_threshold: float = None,
                                                 extra: dict = None) -> Iterator[None]:
    extra = extra or {}
    with record_query_stats() as result:
        yield

    threshold_key_map = [
        (postgres_threshold, POSTGRES),
        (mongo_threshold, MONGO),
        (http_threshold, HTTP),
    ]
    assert len(threshold_key_map) == len(ALL_KEYS)

    for threshold, key in threshold_key_map:
        if not threshold:
            continue

        if result['timespent'][key] > threshold:
            logger.warning(
                'exceeded allowed total spent time (seconds) for context for resource',
                extra={
                    'key (resource)': key,
                    'threshold': threshold,
                    **extra,
                    **result,
                },
            )


@contextlib.contextmanager
def record_query_stats() -> Iterator[dict]:
    token = local_context.set({
        'counts': {
            POSTGRES: 0,
            MONGO: 0,
            HTTP: 0,
        },
        'timespent': {
            POSTGRES: 0,
            MONGO: 0,
            HTTP: 0,
        },
    })

    # I'm yielding empty dict here. On contextmanager exit, this dict will be updated with execution information. I.e.:
    # >>> with monitoring.record_query_stats() as result:
    # >>>     ...
    # >>> assert result == {
    # >>>     'counts': {'http': 0, 'mongo': 1, 'postgres': 0},
    # >>>     'timespent': {'http': 0, 'mongo': 0.000812784000117972, 'postgres': 0}}
    #
    # NOTE: result will be empty everywhere inside context, and became non-empty only after exiting.
    result: dict = {}
    yield result

    result.update(local_context.get())
    local_context.reset(token)

    prev_context = local_context.get()
    if not prev_context:
        return

    # NOTE: Update broader context. This is necessary for nested usages like these:
    # >>> with record_query_stats() as r1:
    # >>>     ...
    # >>>     with record_query_stats() as r2:
    # >>>         ...
    # >>>         with record_query_stats() as r3:
    # >>>             ...
    #
    # If didn't do this, all record_query_stats() would record ONLY calls at first context level, without inner calls.
    for f in ['counts', 'timespent']:
        for k in ALL_KEYS:
            prev_context[f][k] += result[f][k]


__locals = threading.local()
__locals.disable_slow_query_log = False


@contextlib.contextmanager
def disable_slow_query_log() -> Generator[None, None, None]:
    __locals.disable_slow_query_log = True
    yield
    __locals.disable_slow_query_log = False


def wrap(*,
         cls: Type,
         method: str,
         logger_message: str,
         extra_builder: Callable,
         key: str,
         allowed_duration_func: Callable = None,
         ) -> None:
    orig = getattr(cls, method)

    @functools.wraps(orig)
    def patched_method(*args, **kwargs):        # type: ignore
        start = time.monotonic()
        try:
            return orig(*args, **kwargs)
        finally:
            duration = time.monotonic() - start
            allowed_duration = allowed_duration_func(*args, **kwargs) if allowed_duration_func else \
                Config.QUERY_EXECUTION_THRESHOLD_SECONDS
            if duration > allowed_duration and not getattr(__locals, "disable_slow_query_log", False):
                logger.warning(
                    logger_message,
                    extra={
                        'duration': duration,
                        **extra_builder(*args, **kwargs),
                        'traceback': "".join(traceback.format_stack(limit=50)),
                    },
                )

            ctx = local_context.get()
            if ctx:
                ctx['counts'][key] += 1
                ctx['timespent'][key] += duration
                local_context.set(ctx)

    setattr(cls, method, patched_method)


def patch_mongo() -> None:
    from pymongo.cursor import Cursor

    wrap(
        cls=Cursor,
        method='_send_message',
        logger_message='mongo find query execution took too long',
        extra_builder=lambda self, *a, **k: {
            'collection': repr(self._collection.name),
            'operation': repr(self._spec),
        },
        key=MONGO,
        allowed_duration_func=Config.MONGO_ALLOWED_DURATION_FUNC,
    )

    def _command_allowed_duration(self, dbname, spec, *a, **k):     # type: ignore
        if 'topologyVersion' in spec and 'helloOk' in spec:
            return 1000
        return Config.MONGO_ALLOWED_DURATION_FUNC(self, dbname, spec, *a, **k)


def patch_django() -> None:
    from django.db.backends.utils import CursorWrapper

    def query_with_params(sql, params):     # type: ignore
        try:
            return sql % params
        except Exception:
            return '<cant build query with params>'

    wrap(
        cls=CursorWrapper,
        method='_execute_with_wrappers',
        logger_message='django query execution took too long',
        extra_builder=lambda self, sql, params, many, executor: {
            'query': sql,
            'params': params,
            'many': many,
            'query_with_params': query_with_params(sql, params),        # type: ignore
        },
        key=POSTGRES,
        allowed_duration_func=Config.POSTGRES_ALLOWED_DURATION_FUNC,
    )


def patch_requests() -> None:
    from requests import Session

    wrap(
        cls=Session,
        method='send',
        logger_message='http request execution took too long',
        extra_builder=lambda self, request, **kwargs: {
            'method': request.method,
            'url': request.url,
        },
        key=HTTP,
        allowed_duration_func=Config.HTTP_ALLOWED_DURATION_FUNC,
    )
