import logging
import time
from typing import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from rozert_pay.common import metrics

logger = logging.getLogger(__name__)


class LogResponseMiddleware:
    def __init__(self, get_response: Callable) -> None:  # type: ignore[type-arg]
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)

        logfunc = logger.debug
        if 200 <= response.status_code < 300:
            logfunc = logger.debug
        elif 300 <= response.status_code < 400:
            logfunc = logger.debug
        elif 400 <= response.status_code < 500:
            logfunc = logger.warning
            if not settings.IS_UNITTESTS:
                logfunc = logger.exception
        elif 500 <= response.status_code:
            logfunc = logger.exception

        if 400 <= response.status_code < 500:
            logfunc(
                f"4xx response on url {request.build_absolute_uri()} with status code {response.status_code}",
                extra={
                    "status_code": response.status_code,
                    "url": request.build_absolute_uri(),
                    "response": response.content,
                },
            )

        return response


class PrometheusMetricsMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start_time = time.time()

        # Отслеживаем SQL запросы
        with metrics.track_sql_queries():
            response = self.get_response(request)

        # skip if static file
        if request.path.startswith("/static/"):
            return response

        duration = time.time() - start_time
        sql_queries_count = metrics.get_sql_queries_count()

        # use request pattern instead of path
        url = request.path
        resolver_match = request.resolver_match
        if resolver_match:
            url = resolver_match.route

        # Обновляем метрики
        metrics.REQUESTS.labels(
            method=request.method,
            endpoint=url,
            http_status=response.status_code,
        ).inc()
        metrics.REQUESTS_DURATION.labels(
            method=request.method,
            endpoint=url,
            http_status=response.status_code,
        ).observe(duration)
        metrics.HTTP_SQL_QUERIES.labels(
            method=request.method,
            endpoint=url,
            http_status=response.status_code,
        ).observe(sql_queries_count)

        return response
