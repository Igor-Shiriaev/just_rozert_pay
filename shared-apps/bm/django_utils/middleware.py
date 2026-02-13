import logging
import threading
import time
import typing
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Any, Type, cast
from urllib.parse import urlparse, urlunparse
from uuid import uuid4
import threading

from bm.django_utils import monitoring
from bm.django_utils.metrics import validate_influx_tags
from bm.exceptions import HTTPBadRequest, HTTPError, HTTPServerError
from bm.logging import set_logging_context

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse, RawPostDataException
from django.utils.deprecation import MiddlewareMixin
from pydantic import ValidationError
import sentry_sdk
from prometheus_client import Counter, Histogram
from prometheus_client.metrics import MetricWrapperBase


class SessionExpirationMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest) -> None:
        if not settings.DEBUG:
            request.session.set_expiry(settings.MAX_SESSION_DURATION_SECONDS)  # type: ignore


logger = logging.getLogger(__name__)

_lock = threading.Lock()


class JsonResponseMiddleware:
    """ Middleware that handles Dict responses"""

    def __init__(self, get_response):   # type: ignore
        self.get_response = get_response

    def __call__(self, request):    # type: ignore
        response = self.get_response(request)
        if isinstance(response, (List, Dict, type(None))):
            return JsonResponse(response, safe=False)
        return response


class BaseHttpMetricsMiddleware:
    METRIC_PREFIX: str      # Need to define in subclasses
    HEADER_PLATFORM = 'platform'
    # define in subclass set of domain groups that are important to track separately,
    # all other domain groups will be grouped under 'all_other_dg' label.
    DOMAIN_GROUPS_EXPLICIT: list[str]

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response
        self.force_debug_cursor = False
        self.prometheus_metrics = PrometheusHttpMetrics.get_instance(
            namespace=getattr(settings, "PROMETHEUS_METRIC_NAMESPACE", "")
        )

    def _get_request_name(self, request: HttpRequest) -> str:
        """Custom name set via request's `_metric_name` attribute or
        custom url name or
        view name or
        default name.
        """

        # Kenya http integration is implemented as one view receiving sms
        # of different types. In order to distinguish diffenret request types
        # `_metric_name` attr could be added to `request` object.
        if hasattr(request, '_metrics_name'):
            return request._metrics_name  # type: ignore

        default_name = 'unknown'
        if hasattr(request, 'resolver_match'):
            if request.resolver_match is not None:
                if request.resolver_match.url_name:
                    # E.g. admin:betmaster_user_change or
                    # betmaster:bet.single_set.
                    return '%s:%s' % (
                        request.resolver_match.namespace,
                        request.resolver_match.url_name,
                    )
                else:
                    return request.resolver_match.view_name or default_name
        return default_name

    def __call__(self, request: HttpRequest) -> HttpResponse:
        from telegraf.defaults.django import telegraf

        self.prometheus_metrics.requests_total.inc()

        # prepare
        time_start = time.monotonic()
        self.force_debug_cursor = connection.force_debug_cursor
        # Just uses CursorDebugWrapper instead of CursorWrapper
        # (django.db.backends.utils module).
        connection.force_debug_cursor = True

        # process response
        with monitoring.record_query_stats() as stats:
            response = self.get_response(request)

        # cleanup
        connection.force_debug_cursor = self.force_debug_cursor

        # track metric
        # 1 - obsolete influx metrics
        tags = self._get_metric_tags(request, response)
        validate_influx_tags(tags)

        duration = time.monotonic() - time_start
        view_name = tags['name']
        sql_queries_cnt = len(connection.queries)

        fields = {
            'duration': duration,
            'mongo_query_count': float(stats['counts'][monitoring.MONGO]),
            'mongo_timespent': float(stats['timespent'][monitoring.MONGO]),
            'sql_queires_cnt': sql_queries_cnt,
            'sql_time': sum(
                float(q.get('time', 0)) for q in connection.queries
            ) or 0.0,  # zero should be float, not integer
        }
        telegraf.track(
            name=self._get_metric_name(),
            tags=tags,
            fields=fields
        )

        # 2 - new prometheus metrics
        domain_group = self.get_request_domain_group(request)
        http_api_mode: str
        if (http_api_mode_setting := getattr(settings, 'HTTP_API_MODE', None)) is not None:
            http_api_mode = http_api_mode_setting.value
        else:
            http_api_mode = 'api_mode_default'
        self.prometheus_metrics.requests_latency.labels(
            api_mode=http_api_mode,
            name=view_name,
            status=str(tags['status']),
            domain_group=domain_group,
        ).observe(duration)
        self.prometheus_metrics.sql_queries_per_request.labels(
            api_mode=http_api_mode,
            name=view_name,
            domain_group=domain_group,
        ).observe(sql_queries_cnt)

        # finish response processing
        return response

    def get_request_domain_group(self, request: HttpRequest) -> str:
        domain_group = request.META.get('HTTP_X_INSTANCE')
        if domain_group not in self.DOMAIN_GROUPS_EXPLICIT:
            return 'all_other_dg'
        else:
            return domain_group

    def _get_metric_name(self) -> str:
        return f'{self.METRIC_PREFIX}.http_request.processed'

    def _get_metric_tags(self, request: HttpRequest, response: HttpResponse) -> dict[str, typing.Any]:
        tags = {
            'name': self._get_request_name(request),
            'host': request.get_host(),
            'platform': getattr(request, 'vendor_headers', defaultdict(str))[self.HEADER_PLATFORM] or '<unknown>',  # type: ignore
            'method': request.method,
            'status': response.status_code,
            # 'is_authorized': not request.user.is_anonymous,
        }
        return tags


class ErrorHandleMiddleware(MiddlewareMixin):
    def __init__(self, get_response):   # type: ignore
        self.get_response = get_response

    def process_view(self, request, view_func, view_args, view_kwargs): # type: ignore
        try:
            response = view_func(request, *view_args, **view_kwargs)
            if isinstance(response, HTTPError):
                logger.warning('returned http error', extra={
                    '_error': response.as_data(),
                })
                return self.handle_error(response)
            return response
        except HTTPError as e:
            logger.warning('raised http error', extra={
                '_error': e.as_data(),
            })
            return self.handle_error(e)
        except ValidationError as e:
            logger.warning(
                'raised pydantic validation error',
                extra={
                    '_error': e,
                    '_payload': getattr(request, 'payload', None),
                    '_GET': request.GET,
                    '_POST': request.POST,
                },
            )
            return self.handle_error(HTTPBadRequest(
                detail=e.errors(),          # type: ignore
            ))
        except Exception as e:
            try:
                body = request.body
            except RawPostDataException:
                body = request.POST
            logger.exception(
                'unhandled http error',
                extra={
                    '_error': e,
                    '_body': body,
                },
            )
            return self.handle_error(HTTPServerError())

    def handle_error(self, error: HTTPError) -> JsonResponse:
        resp = JsonResponse(error.as_data(), safe=False)
        resp.status_code = error.status
        return resp


_locals = threading.local()


class RequestIdMiddleware(MiddlewareMixin):
    def __init__(self, get_response):   # type: ignore
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.META.get('HTTP_X_REQUEST_ID', None) or f"middleware:{uuid4()}"
        set_request_id(request_id)

        with set_logging_context(reqid=get_request_id()):
            scope = sentry_sdk.get_isolation_scope()
            scope.set_tag('req_id', get_request_id())
            try:
                return self.get_response(request)   # type: ignore
            finally:
                set_request_id(None)


class RefererTagMiddleware:
    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        referer = request.META.get('HTTP_REFERER')
        if referer:
            parsed = urlparse(referer)
            cleaned = parsed._replace(query="", fragment="")
            cleaned_referer = urlunparse(cleaned)
            scope = sentry_sdk.get_isolation_scope()
            scope.set_tag("http.referer", cleaned_referer)
        return self.get_response(request)


def set_request_id(request_id: Optional[str]) -> None:
    _locals.request_id = request_id


def get_request_id() -> Optional[str]:
    return getattr(_locals, 'request_id', None)


PROMETHEUS_HTTP_LATENCY_BUCKETS = (
    # 10ms resolution
    0.01, 0.02, 0.03,

    # 25ms resolution
    0.05, 0.075, 0.1,

    # 50ms resolution
    0.15, 0.2, 0.25,

    # 250ms resolution
    0.5, 0.75, 1.0,

    # tail
    1.5, 2.5, 5.0,
)
PROMETHEUS_SQL_QUERIES_BUCKETS = (0, 1, 3, 5, 10, 15, 25, 35, 50, 75, 100, 250, 500, 1000, 2500, 5000)


class PrometheusHttpMetrics:
    _instance: Optional['PrometheusHttpMetrics'] = None

    # NOTE: it's a good practice to have simple counter metric on top of
    # requests histogram. 1 - it's accumulated before request processing. 2 - 
    # it's much more compact/faster for simple cases than histogram summarization
    # across all labels and buckets.
    # That's why we have both `requests_total` counter and `requests_latency` histogram metrics here.
    requests_total: Counter
    requests_latency: Histogram
    sql_queries_per_request: Histogram

    @classmethod
    def get_instance(cls, namespace: str) -> 'PrometheusHttpMetrics':
        if not cls._instance:
            with _lock:
                if not cls._instance:
                    cls._instance = cls(namespace)
        return cls._instance

    def register_metric(self, metric_cls: Type[MetricWrapperBase], name: str, documentation: str, labelnames: tuple[str, ...] = (), **kwargs: Any) -> MetricWrapperBase:
        return metric_cls(name, documentation, labelnames=labelnames, **kwargs)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.latency_buckets = getattr(settings, "PROMETHEUS_HTTP_LATENCY_BUCKETS", PROMETHEUS_HTTP_LATENCY_BUCKETS)
        self.sql_queries_buckets = getattr(
            settings,
            "PROMETHEUS_SQL_QUERIES_BUCKETS",
            PROMETHEUS_SQL_QUERIES_BUCKETS,
        )
        self.register(*args, **kwargs)

    def register(self, namespace: str) -> None:
        self.requests_total = cast(Counter, self.register_metric(
            Counter,
            "http_requests_total",
            "Total number of received HTTP requests",
            namespace=namespace,
        ))
        self.requests_latency = cast(Histogram, self.register_metric(
            Histogram,
            "http_requests_latency_seconds",
            "Histogram of requests processing time (including middleware processing time).",
            buckets=self.latency_buckets,
            labelnames=("api_mode", "name", "status", "domain_group"),
            namespace=namespace,
        ))
        self.sql_queries_per_request = cast(Histogram, self.register_metric(
            Histogram,
            "http_sql_queries_per_request",
            "Number of SQL requests per HTTP request.",
            buckets=self.sql_queries_buckets,
            labelnames=("api_mode", "name", "domain_group"),
            namespace=namespace,
        ))
