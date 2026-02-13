import contextlib
import logging
import time
import traceback
from typing import Dict, Union, Callable, Any, cast, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def safe_assert(
    assert_func_or_bool: Union[bool, Callable[[], bool]],
    msg: str,
    loglevel: int = logging.ERROR,
    stack_info: bool = True,
    break_flow_in_dev: bool = True,
    **extra: Any,
) -> None:
    assert_: Callable[[], bool]

    if isinstance(assert_func_or_bool, bool):
        assert_ = lambda: assert_func_or_bool  # type: ignore
    else:
        assert_ = assert_func_or_bool


    if cast(Any, settings).IS_PRODUCTION or not break_flow_in_dev:
        if not assert_():
            if stack_info:
                # Adds current traceback to extra
                extra['traceback'] = traceback.format_stack()

            logger.log(
                loglevel, msg, extra=extra, stack_info=True
            )

        return

    assert assert_(), f'{msg}, extra={extra}'


def track(name: str, fields: Dict, tags: Optional[dict[str, str]] = None) -> None:
    for key, value in (tags or {}).items():
        safe_assert(bool(value), f'empty tag value for key {key} {value}')
        safe_assert(isinstance(value, str), f'not str tag value for key {key} {value}')

    if not getattr(settings, 'METRICS_TRACKING_ENABLED', False):
        logger.debug('fake sending metrics to telegraf', extra={
            '_name': name,
            '_fields': fields,
            '_tags': tags,
        })
        return

    from telegraf.defaults.django import telegraf

    try:
        telegraf.track(
            name=name,
            fields=fields,
            tags=tags,
        )
    except Exception as e:
        logger.exception(
            'exception while track metric',
            extra={
                '_name': name,
                '_fields': fields,
                '_tags': tags,
                '_error': e,
                '_error_info': e.__dict__,
            }
        )


def validate_influx_tags(tags: dict) -> None:
    for key, tag in tags.items():
        if tag == '':
            logger.error('received empty influx tag. It can cause metric drop, '
                         'see https://app.shortcut.com/betmaster/story/97552/http-messaging', extra={
                '_tags': tags,
                '_key': key,
                '_traceback': traceback.format_stack(),
            })


@contextlib.contextmanager
def timer_context(name: str, fields: Optional[Dict] = None, tags: Optional[Dict] = None):   # type: ignore
    start = time.monotonic()
    error = None

    fields = fields if fields is not None else {}
    tags = tags if tags is not None else {}

    validate_influx_tags(tags)

    try:
        yield
    except Exception as e:
        error = e
        raise
    finally:
        if error:
            tags['error'] = error.__class__.__name__

        track(
            name=name,
            fields={
                'duration': time.monotonic() - start,
                **fields,
            },
            tags=tags
        )
