import datetime
import decimal
import functools
import json
import logging
import ssl
import string
import time
import typing
import uuid
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
    cast,
)
from unittest.mock import Mock

import requests
from bm.exceptions import NonReportableValueError, ValidationError
from bm.typing_utils import T_Callable
from pydantic import BaseModel
from requests import PreparedRequest
from requests.adapters import HTTPAdapter
from urllib3 import PoolManager
from urllib3.util.retry import Retry

from .serializers import serialize_decimal

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from bm.typing_utils import T_Decorated_Function


def instance_as_data(instance: Any) -> Any:  # type: ignore
    # To avoid infinite recursion in tests
    assert not isinstance(instance, Mock)  # type: ignore
    if hasattr(instance, 'as_data'):
        return instance_as_data(instance.as_data())
    if isinstance(instance, BaseModel):
        return {k: instance_as_data(v) for k, v in instance.dict().items()}
    if is_dataclass(instance):
        return {k: instance_as_data(v) for k, v in asdict(instance).items()}  # type: ignore[arg-type]
    if isinstance(instance, dict):
        return {k: instance_as_data(v) for k, v in instance.items()}
    if isinstance(instance, Enum):
        return instance.value
    if isinstance(instance, (list, tuple, set)):
        return [instance_as_data(v) for v in instance]
    return instance


# Pay attention - this code in use in migrations so do not move/remove it without changing usage in migrations.
class JSONEncoder(json.JSONEncoder):
    def default(self, o):  # type: ignore
        # See "Date Time String Format" in the ECMA-262 specification.
        if isinstance(o, datetime.datetime):
            r = o.isoformat()
            if o.microsecond:
                r = r[:23] + r[26:]
            if r.endswith('+00:00'):
                r = r[:-6] + 'Z'
            return r
        elif isinstance(o, datetime.date):
            return o.isoformat()
        elif isinstance(o, datetime.time):
            if o.utcoffset() is not None:
                raise ValueError("JSON can't represent timezone-aware times.")
            r = o.isoformat()
            if o.microsecond:
                r = r[:12]
            return r
        elif isinstance(o, uuid.UUID):
            return str(o)
        elif isinstance(o, decimal.Decimal):
            return format(o, 'f')
        elif hasattr(o, '__json__'):
            return o.__json__()
        else:
            return super().default(o)


class BMJsonEncoder(json.JSONEncoder):
    def default(self, obj):     # type: ignore
        if isinstance(obj, decimal.Decimal):
            return serialize_decimal(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime.datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, datetime.date):
            return obj.strftime('%Y-%m-%d')
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, '__json__'):
            return obj.__json__()
        return super().default(obj)


def json_dumps(value: Any) -> str:  # type: ignore
    return json.dumps(value, cls=JSONEncoder)


def json_loads(value: Union[str, bytes]) -> Union[Dict, List]:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        raise ValidationError('Payload parsing error')


def round_decimal(
    value: Union[Decimal, float],
    places: Optional[int] = 2,
    rounding: Optional[str] = None
) -> Decimal:
    # TODO: get rid of this hack
    if not isinstance(value, Decimal):
        logger.warning(
            'attempt to round non-decimal as decimal',
            extra={'d': value, 'type': type(value).__name__}
        )
        value = Decimal(value)
    return quantize_decimal(value=value, places=places, rounding=rounding)


DECIMAL_PRECISION_CTX = decimal.Context(
    prec=31,
    rounding=decimal.ROUND_HALF_EVEN,
    traps=[
        decimal.DivisionByZero,
        decimal.FloatOperation,
        decimal.InvalidOperation,
        decimal.Overflow,
    ]
)

_DECIMAL_PLACES_MAP = {i: Decimal(10) ** -i for i in range(0, 19)}


def quantize_decimal(
    value: Decimal,
    places: Optional[int],
    rounding: Optional[str] = None
) -> Decimal:
    if places is None:
        return value
    return value.quantize(
        _DECIMAL_PLACES_MAP[places],
        rounding=rounding,
        context=DECIMAL_PRECISION_CTX
    )


class TimeoutedHttpAdapter(HTTPAdapter):
    DEFAULT_TIMEOUT_SECONDS = (5, 10)

    def send(
        self,
        request: PreparedRequest,
        *args: Any,
        **kwargs: Any,
    ) -> requests.Response:
        if not kwargs.get('timeout'):
            kwargs['timeout'] = self.DEFAULT_TIMEOUT_SECONDS
        return super().send(request, *args, **kwargs)


class HTTPAdapterTLSv12(TimeoutedHttpAdapter):
    poolmanager: PoolManager

    def init_poolmanager(  # type: ignore
        self,
        connections: int,
        maxsize: int,
        block: bool = False,
        **pool_kwargs: Any
    ) -> None:
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            strict=True,
            ssl_version=ssl.PROTOCOL_TLSv1_2,
        )


def requests_retry_session(
    retries: int = 3,
    backoff_factor: float = 0.3,
    status_forcelist: Sequence[int] = (500, 502, 504),
    session: Optional[requests.Session] = None,
    adapter_class: Type[HTTPAdapter] = TimeoutedHttpAdapter,
    pool_maxsize: Optional[int] = None,
) -> requests.Session:
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )

    adapter_kwargs: dict[str, Any] = {'max_retries': retry}
    if pool_maxsize is not None:
        adapter_kwargs['pool_maxsize'] = pool_maxsize

    adapter = adapter_class(**adapter_kwargs)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def log_errors(func: T_Callable) -> T_Callable:
    @functools.wraps(func)
    def on_call(*args, **kwargs):  # type: ignore
        try:
            return func(*args, **kwargs)
        except NonReportableValueError as e:
            logger.warning(
                'Error',
                extra={
                    'error_class_name': e.__class__.__name__,
                    'function_name': func.__name__,
                    'exception': e,
                },
            )
            raise
        except Exception as e:
            logger.exception(
                'Error: %s in function %s',
                e.__class__.__name__,
                func.__name__,
            )
            raise

    return on_call  # type: ignore


def enum_as_choices(
    enum: Type[Enum],
    exclude: Optional[List[Enum]] = None,
    sort: bool = False,
) -> List[Tuple[Union[str, int], str]]:
    choices = []
    exclude = exclude or []
    for item in enum:
        if item in exclude:
            continue
        choices.append((
            item.value,
            item.name.replace('_', ' ').lower().capitalize()
        ))

    if sort:
        choices.sort(key=lambda i: i[1])
    return choices


def retry(max_tries: int, interval: int) -> Callable[[T_Callable], T_Callable]:
    def on_dec(func: T_Callable) -> T_Callable:
        @functools.wraps(func)
        def on_call(*args: Any, **kwargs: Any) -> Any:  # type: ignore
            error = None
            for i in range(1, max_tries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if i < max_tries:
                        time.sleep(interval)
                    error = exc
            if error is not None:
                raise error

        return cast(T_Callable, on_call)

    return on_dec


def format_datetime(datetime_: datetime.datetime) -> str:
    return datetime_.strftime("%d-%m-%Y %H:%M:%S.%f")[:-3]


def timestamp_to_millis(ts: Union[int, float]) -> int:
    return int(ts * 1000)


def datetime_to_millis(dt: datetime.datetime) -> int:
    return int(dt.timestamp() * 1000)


def optional_datetime_to_millis(dt: Optional[datetime.datetime]) -> Optional[int]:
    if dt is None:
        return None
    return datetime_to_millis(dt)


def datetime_to_seconds(dt: datetime.datetime) -> int:
    return int(dt.timestamp())


def optional_datetime_to_seconds(dt: Optional[datetime.datetime]) -> Optional[int]:
    if dt is None:
        return None
    return int(dt.timestamp())


class ReprMixin:
    repr_fields: Optional[List[str]] = None
    separator: str = ', '

    def __repr__(self) -> str:  # type: ignore
        fields = self.repr_fields or sorted(self.__dict__.keys())

        parts = []

        for field in fields:
            value = getattr(self, field)
            parts.append(f'{field}={value!r}')

        return f'{self.__class__.__name__}({self.separator.join(parts)})'

    def __str__(self) -> str:
        return self.__repr__()


T = typing.TypeVar('T')


def split_iterable(iterable: typing.Iterable[T], n: int) -> typing.Iterator[Sequence[T]]:
    bulk = []

    for item in iterable:
        bulk.append(item)
        if len(bulk) >= n:
            yield bulk
            bulk = []

    if bulk:
        yield bulk


ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits + '-_'
ALPHABET_REVERSE = dict((c, i) for (i, c) in enumerate(ALPHABET))
BASE = len(ALPHABET)


def encode_integer_to_shortest_string(n: int) -> str:
    s = []
    while True:
        n, r = divmod(n, BASE)
        s.append(ALPHABET[r])
        if n == 0:
            break
    return ''.join(reversed(s))


def decode_shortest_string_to_integer(s: str) -> int:
    n = 0
    for c in s:
        n = n * BASE + ALPHABET_REVERSE[c]
    return n


T_Decorator = typing.TypeVar('T_Decorator', bound=Callable)


def include_original(
    dec: T_Decorator
) -> Callable[['T_Decorated_Function'], Callable[['T_Decorated_Function'], 'T_Decorated_Function']]:
    def meta_decorator(
        f: 'T_Decorated_Function'
    ) -> Callable[['T_Decorated_Function'], 'T_Decorated_Function']:
        decorated = dec(f)
        decorated._original = f
        return decorated

    return meta_decorator


def get_pydantic_model_fields(model: Type[BaseModel]) -> list[tuple[str, str, bool]]:
    """Get fields of a Pydantic model as a list of tuples (name, type, mandatory)."""

    return [
        (  # type: ignore[misc]
            field_name,
            str(field.annotation) if field.sub_fields else str(field.type_.__name__),
            field.required or False,
        )
        for field_name, field in model.__fields__.items()
    ]
