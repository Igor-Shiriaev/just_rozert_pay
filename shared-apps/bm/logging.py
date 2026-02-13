import contextlib
import contextvars
import datetime
import logging
import re
import os
import typing
from decimal import Decimal
from functools import partial
from logging import LogRecord
from typing import TYPE_CHECKING, Any, Callable, MutableMapping, Optional, Union, cast

from bm.django_utils import metrics
from django.conf import settings
from django.http.cookie import SimpleCookie
from pydantic import BaseModel
from pytz import utc

try:
    import ujson
except ImportError:
    import json as ujson  # type: ignore

if TYPE_CHECKING:
    from types import TracebackType

    from django.http import HttpRequest


CARD_CVV_REGEXP = r'^\d{3,4}$'
CARD_NUMBER_REGEXP = r'^\d{15,19}$'


GOOD_TYPES_FOR_SERIALIZATION = (
    int, str, float, Decimal,
    bool, type(None),
)


RESERVED_ATTRS = (
    'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
    'funcName', 'levelname', 'levelno', 'lineno', 'module',
    'msecs', 'message', 'msg', 'name', 'pathname', 'process',
    'processName', 'relativeCreated', 'stack_info', 'thread', 'threadName'
)


_HIDDEN_VALUE_PATHS: tuple[tuple[str, ...], ...] = (
    ('password',),
    ('password_confirm',),
    ('card', 'num'),
    ('card', 'cvv'),
    ('wallet', 'card', 'num'),
    ('wallet', 'card', 'cvv'),
)


_EXC_INFO_LOCALS_ATTRS_TO_HIDE: list[str] = []


def serialize_for_log(value: typing.Any) -> typing.Any:
    """ujson dumps works not very well with custom classes.
    So for each non-trvial type we should convert it to repr string
    before serialization.
    """
    if isinstance(value, GOOD_TYPES_FOR_SERIALIZATION):
        return value
    return repr(value)


class PrivateFieldDescription(BaseModel):
    key: str
    pattern: Optional[str] = None

    hide_func: Optional[Callable[[str], str]] = None

    def hide(self, value):      # type: ignore
        if self.hide_func:
            return self.hide_func(value)
        return '<hidden>'

    def matches(self, value: str) -> bool:
        assert isinstance(value, str)
        if self.pattern is None:
            return True
        return bool(re.match(self.pattern, value))


_PRIVATE_DATA_FIELDS = [
    PrivateFieldDescription(key='password'),
    PrivateFieldDescription(key='cvv', pattern=CARD_CVV_REGEXP),
    PrivateFieldDescription(key='num', pattern=CARD_NUMBER_REGEXP,
                            hide_func=lambda s: f'{s[:6]}*******{s[-4:]}')
]


def make_private_data_fields_dict(private_data_fields: list[PrivateFieldDescription]) -> dict[str, PrivateFieldDescription]:
    return {
        item.key: item
        for item in private_data_fields
    }


PRIVATE_DATA_FIELDS = make_private_data_fields_dict(_PRIVATE_DATA_FIELDS)


def maybe_hide_private_data(*, data: dict, fields_to_hide: dict[str, PrivateFieldDescription]) -> dict:
    out: dict = {}

    for key, value in data.items():
        if isinstance(value, dict):
            out[key] = maybe_hide_private_data(data=value, fields_to_hide=fields_to_hide)
        # NOTE: refactor this, maybe add additional argument from the client if it's really needed here.
        elif os.environ.get('HTTP_API_MODE') == 'admin-panel' and isinstance(value, list):
            out[key] = []
            for item in value:
                if isinstance(item, dict):
                    out[key].append(maybe_hide_private_data(data=item, fields_to_hide=fields_to_hide))
                else:
                    out[key].append(item)
        elif key in fields_to_hide and fields_to_hide[key].matches(str(value)):
            out[key] = fields_to_hide[key].hide(str(value))     # type: ignore
        else:
            out[key] = value

    return out


_bound_global_logging_context: contextvars.ContextVar[dict] = contextvars.ContextVar('bound_global_logging_context', default={})
_bound_local_logging_contexts: contextvars.ContextVar[list[dict]] = contextvars.ContextVar('bound_local_logging_context', default=[])


def set_global_logging_context(**context: typing.Any) -> None:
    data = _bound_global_logging_context.get()
    assert len(data) < 100
    data.update(context)
    _bound_global_logging_context.set(data)


def clear_global_logging_context() -> None:
    _bound_global_logging_context.set({})


@contextlib.contextmanager
def set_logging_context(**context: typing.Any) -> typing.Iterator:
    try:
        contexts = _bound_local_logging_contexts.get()
        assert len(contexts) < 100
        for c in contexts:
            assert len(c) < 100

        contexts.append(context)
        _bound_local_logging_contexts.set(contexts)
        yield
    finally:
        contexts = _bound_local_logging_contexts.get()
        contexts.remove(context)
        _bound_local_logging_contexts.set(contexts)


class BaseBmFormatter(logging.Formatter):
    exclude_attrs = ['msecs', 'relativeCreated', 'exc_text', 'stack_info', 'levelno', 'filename',
                     'module', 'process', 'msg', 'args']
    def get_current_request(self) -> Optional['HttpRequest']:
        return None

    @classmethod
    def log_record_to_dict(cls, log_record: logging.LogRecord, request: Optional['HttpRequest']) -> dict:
        result = log_record.__dict__

        if request:
            result = cls.merge_request_data(target=result, request=request)

        result = cls._add_context_data(result)

        result = maybe_hide_private_data(data=result, fields_to_hide=PRIVATE_DATA_FIELDS)

        metrics_tags = result.get(METRICS_HANDLER_TAGS_KEY)

        result = {
            key: serialize_for_log(value)
            for key, value in result.items()
            if key not in cls.exclude_attrs
        }

        if metrics_tags:
            result[METRICS_HANDLER_TAGS_KEY] = metrics_tags

        return result

    @classmethod
    def _add_context_data(cls, result: dict) -> dict:
        for key, value in _bound_global_logging_context.get().items():
            result[key] = value

        for ctx in _bound_local_logging_contexts.get():
            for key, value in ctx.items():
                result[key] = value

        return result

    @classmethod
    def merge_request_data(cls, *, target: dict, request: 'HttpRequest') -> dict:
        target['http_request_id'] = request.META.get('HTTP_X_REQUEST_ID')
        target['http_method'] = request.method
        target['http_uri'] = request.path

        if not target['name'].startswith('django'):
            user = getattr(request, 'user', None)
            if user and user.is_authenticated:
                target['http_request_user_id'] = str(getattr(user, 'uuid', str(user)))

        return target

class JsonFormatter(BaseBmFormatter):
    def __init__(self, *args, **kwargs):        # type: ignore
        self.pretty = kwargs.pop('pretty', False)
        logging.Formatter.__init__(self, *args, **kwargs)
        self.datefmt = self.datefmt or '%Y-%m-%d %H:%M:%S.%Z'

    def format(self, record):       # type: ignore
        message_dict = {}
        if isinstance(record.msg, dict):
            message_dict = dict(record.msg)
            record.message = None
        else:
            record.message = record.getMessage()

        log_data_dict = self.log_record_to_dict(record, request=self.get_current_request())

        log_data_dict['timestamp'] = datetime.datetime.fromtimestamp(
            record.created, tz=utc).strftime(self.datefmt)

        if record.exc_info:
            log_data_dict['exc_info'] = self.formatException(record.exc_info)

        if self.pretty:
            dump_func = partial(ujson.dumps, indent=2)
        else:
            dump_func = ujson.dumps

        return dump_func(log_data_dict, ensure_ascii=False)


class KeyValueFormatter(BaseBmFormatter):
    """ Adds extra as key=value pairs.
    """
    base_record_keys = list(
        logging.LogRecord(
            None, None, None, None, None, None, None).__dict__.keys()   # type: ignore
    ) + ['message', 'asctime']

    def format(self, record):   # type: ignore
        base = super().format(record)

        parts = []

        for key, value in self.log_record_to_dict(record, request=self.get_current_request()).items():
            if isinstance(value, float):
                value = round(value, 4)

            parts.append(self._make_part(key, value))

        return f'{base}\t\t{" ".join(parts)}'

    def _make_part(self, key, value):       # type: ignore
        return f'{key}={value!r}'


class MetricsHandlerFormatter(BaseBmFormatter):
    exclude_attrs = tuple()     # type: ignore


METRICS_HANDLER_TAGS_KEY = '_metrics_handler_tags'


class MetricsHandler(logging.StreamHandler):
    formatter: MetricsHandlerFormatter

    def __init__(
        self, prefix: str,
        tags: Optional[list[str]] = None,
        fields: Optional[list[str]] = None,
    ):
        self.prefix = prefix
        self.tags = tags or [
            'funcName',
            'filename',
            'module',
            'name',
        ]
        self.fields = fields or []
        super().__init__()
        self.formatter = MetricsHandlerFormatter()

    def emit(self, record: LogRecord) -> None:
        data = self.formatter.log_record_to_dict(record, self.get_current_request())
        self._track(
            f'{self.prefix}:logmetrics_v2',
            fields=self._get_fields(data),
            tags=self._get_tags(data),
        )

    def _track(self, *args: Any, **kwargs: Any) -> None:
        metrics.track(*args, **kwargs)

    def _get_tags(self, data: dict) -> dict:
        tags = {k: v for k, v in data.items() if k in self.tags}

        if custom_tags := data.get(METRICS_HANDLER_TAGS_KEY):
            tags.update({
                k: repr(v) or '<no value>'
                for k, v in custom_tags.items()
            })

        return tags

    def _get_fields(self, data: dict) -> dict:
        base = {
            k: v for k, v in data.items() if k in self.fields
        }
        return {
            'count': 1,
            **base,
        }

    def get_current_request(self) -> Optional['HttpRequest']:
        return None


def _maybe_hide_private_data_in_payload(payload: dict) -> None:
    for path in _HIDDEN_VALUE_PATHS:
        root: dict = payload
        for element in path[:-1]:
            if element not in root:
                break
            new_root = root[element]
            if not isinstance(new_root, dict):
                break
            root = new_root
        else:
            if path[-1] in root:
                root[path[-1]] = '<hidden>'


ExcInfoType = tuple[type[BaseException], BaseException, Optional['TracebackType']]


def _maybe_hide_private_data_in_exc_info(
    exc_info: Optional[Union[ExcInfoType, tuple[None, None, None]]]
) -> None:
    if not exc_info or exc_info[2] is None:
        return

    tb_item: Optional['TracebackType'] = exc_info[2]
    while tb_item:
        locals = tb_item.tb_frame.f_locals
        for loc in locals:
            for attr in _EXC_INFO_LOCALS_ATTRS_TO_HIDE:
                if hasattr(locals[loc], attr):
                    setattr(locals[loc], attr, '<hidden>')
        tb_item = cast('TracebackType', tb_item).tb_next


def scrub_request_data(request: dict) -> dict:
    if 'body' in request:
        try:
            payload = ujson.loads(request['body'])
            _maybe_hide_private_data_in_payload(payload)
            request['body'] = ujson.dumps(payload, ensure_ascii=False)
        except ValueError:
            # raises for non 'application/json' requests
            pass

    if 'Cookie' in request['headers']:
        cookie = SimpleCookie(request['headers']['Cookie'])
        if settings.SESSION_COOKIE_NAME in cookie:
            sid = cookie[settings.SESSION_COOKIE_NAME].value
            if ':' in sid:
                cookie[settings.SESSION_COOKIE_NAME] = sid.split(':')[0] + ':<hidden>'
                request['headers']['Cookie'] = cookie.output(header='', sep='')

    return request


class LoggingPrefixAdapter(logging.LoggerAdapter):
    def __init__(self, logger: logging.Logger, prefix: str) -> None:
        super().__init__(logger, {})
        self.prefix = prefix

    def process(self, msg: str, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        return f'{self.prefix} {msg}', kwargs


def add_logger_prefix(logger: logging.Logger, prefix: str) -> logging.Logger:
    return cast(logging.Logger, LoggingPrefixAdapter(logger, prefix))
