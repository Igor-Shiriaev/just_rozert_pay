import logging
import os
import pathlib
import threading
import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Generator, Iterable, TypeVar

from django.conf import settings
from django.db import connection
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Metric,
    multiprocess,
)
from prometheus_summary import Summary  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Thread-local storage для хранения счетчиков SQL запросов
_sql_query_counters = threading.local()


class EnvLabelRegistry(CollectorRegistry):
    def collect(self) -> Iterable[Metric]:
        for metric in super().collect():
            for m in metric.samples:
                # Добавляем только env, без process_id
                m.labels.update(
                    {
                        "env": "production" if settings.IS_PRODUCTION else "dev",
                    }
                )
            yield metric


def _build_registry() -> CollectorRegistry:
    """
    Создаёт registry с поддержкой multiprocess, если задан PROMETHEUS_MULTIPROC_DIR.
    """
    registry: CollectorRegistry = EnvLabelRegistry()
    if p := os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        logger.info("Using prometheus multiproc dir: %s", p)
        path = pathlib.Path(p)
        if not path.exists():
            path.mkdir(exist_ok=True, parents=True)
            logger.warning("Created new dir: %s", p)

        try:
            multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        except Exception:
            logger.exception("Unable to use multiprocess collector for prometheus")
    return registry


prometheus_registry = _build_registry()


# Явно заданные 20 бакетов от 0.05 до 10 секунд, с большей плотностью на малых значениях
HISTOGRAM_BUCKETS_20 = [
    0.05,
    0.075,
    0.1,
    0.15,
    0.2,
    0.3,
    0.4,
    0.5,
    0.65,
    0.8,
    1.0,
    1.25,
    1.6,
    2.0,
    2.5,
    3.2,
    4.0,
    5.0,
    7.5,
    10.0,
    13.0,
    16.0,
    19.0,
    25.0,
    30.0,
    40.0,
    50.0,
    60.0,
]

REQUESTS = Counter(
    "rozert_http_requests_total",
    "Total HTTP Requests",
    ["method", "endpoint", "http_status"],
    registry=prometheus_registry,
)
REQUESTS_DURATION = Histogram(
    "rozert_http_request_duration_seconds",
    "HTTP request duration in seconds (histogram)",
    ["method", "endpoint", "http_status"],
    registry=prometheus_registry,
    buckets=HISTOGRAM_BUCKETS_20,
)
HTTP_SQL_QUERIES = Histogram(
    "rozert_http_sql_queries_total",
    "Number of SQL queries per HTTP request",
    ["method", "endpoint", "http_status"],
    registry=prometheus_registry,
    buckets=[0, 1, 2, 3, 5, 10, 15, 20, 30, 50, 100, 200, 500, 1000],
)

TASKS_COUNT = Counter(
    "rozert_tasks_count",
    "Total tasks count",
    [
        "task_name",
        "queue",
        "status",
        "exception",
    ],
    registry=prometheus_registry,
)
TASK_DURATION = Histogram(
    "rozert_task_duration_seconds",
    "Duration of tasks in seconds (histogram)",
    [
        "task_name",
        "queue",
        "status",
        "exception",
    ],
    registry=prometheus_registry,
    buckets=HISTOGRAM_BUCKETS_20,
)
TASK_SQL_QUERIES = Histogram(
    "rozert_task_sql_queries_total",
    "Number of SQL queries per Celery task",
    [
        "task_name",
        "queue",
        "status",
        "exception",
    ],
    registry=prometheus_registry,
    buckets=[0, 1, 2, 3, 5, 10, 15, 20, 30, 50, 100, 200, 500, 1000],
)

DEPOSIT_COUNT = Counter(
    "rozert_deposit_count",
    "Total deposit count",
    [
        "status",
        "system",
    ],
    registry=prometheus_registry,
)

INCOMING_CALLBACK_COUNT = Counter(
    "rozert_callback_count",
    "Total callback count",
    [
        "status",
        "system",
    ],
    registry=prometheus_registry,
)
INCOMING_CALLBACKS_DURATION = Histogram(
    "rozert_callbacks_duration_seconds",
    "Duration of callbacks in seconds (histogram). "
    "This is not a duration of HTTP request, but duration of whole callback handling.",
    [
        "status",
        "system",
    ],
    registry=prometheus_registry,
    buckets=HISTOGRAM_BUCKETS_20,
)

OUTCOMING_CALLBACK_COUNT = Counter(
    "rozert_outcoming_callback_count",
    "Total outcoming callback count",
    [
        "status",
        "system",
    ],
    registry=prometheus_registry,
)
OUTCOMING_CALLBACKS_DURATION = Histogram(
    "rozert_outcoming_callbacks_duration_seconds",
    "Duration of outcoming callbacks in seconds (histogram)",
    [
        "status",
        "system",
    ],
    registry=prometheus_registry,
    buckets=HISTOGRAM_BUCKETS_20,
)

# RabbitMQ queues metrics
RABBIT_QUEUE_MESSAGES = Gauge(
    "rozert_rabbit_queue_messages",
    "Number of messages in RabbitMQ queue",
    ["queue", "vhost"],
    registry=prometheus_registry,
)
RABBIT_QUEUE_CONSUMERS = Gauge(
    "rozert_rabbit_queue_consumers",
    "Number of consumers for RabbitMQ queue",
    ["queue", "vhost"],
    registry=prometheus_registry,
)
RABBIT_QUEUE_MESSAGES_UNACKED = Gauge(
    "rozert_rabbit_queue_messages_unacked",
    "Number of unacked messages in RabbitMQ queue",
    ["queue", "vhost"],
    registry=prometheus_registry,
)
RABBIT_QUEUE_MESSAGES_READY = Gauge(
    "rozert_rabbit_queue_messages_ready",
    "Number of ready messages in RabbitMQ queue",
    ["queue", "vhost"],
    registry=prometheus_registry,
)

RISK_REPO_QUERY_DURATION = Summary(
    "rozert_risk_repo_query_duration_seconds",
    "Duration of risk list repository query (get active entries)",
    ["name"],
    registry=prometheus_registry,
)

EXTERNAL_API_REQUESTS = Counter(
    "rozert_external_api_requests_total",
    "Total external API requests count",
    ["method", "status_code"],
    registry=prometheus_registry,
)
EXTERNAL_API_REQUESTS_DURATION = Histogram(
    "rozert_external_api_request_duration_seconds",
    "External API request duration in seconds (histogram)",
    ["method", "status_code"],
    registry=prometheus_registry,
    buckets=HISTOGRAM_BUCKETS_20,
)

_FUNCTION_DURATION = Histogram(
    "rozert_functions_duration",
    "Duration of different functions",
    ["label", "function"],
    registry=prometheus_registry,
)
_FUNCTION_COUNT = Counter(
    "rozert_functions_count",
    "Count of different functions calls",
    ["label", "function"],
)


TC = TypeVar("TC", bound=Callable)  # type: ignore[type-arg]


class track_duration:
    def __init__(self, label: str):
        self.label = label

    def __call__(self, func: TC) -> TC:
        @wraps(func)
        def inner(*args, **kwargs):  # type: ignore
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start
                _FUNCTION_DURATION.labels(
                    label=self.label,
                    function=self.label,
                ).observe(duration)

                _FUNCTION_COUNT.labels(
                    label=self.label,
                    function=self.label,
                ).inc()

        return inner  # type: ignore[return-value]

    def __enter__(self) -> "track_duration":
        self._start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # type: ignore
        duration = time.time() - self._start

        _FUNCTION_DURATION.labels(
            label=self.label,
            function=self.label,
        ).observe(duration)

        _FUNCTION_COUNT.labels(
            label=self.label,
            function=self.label,
        ).inc()

        del self._start


@contextmanager
def track_sql_queries() -> Generator[None, None, None]:
    """
    Контекстный менеджер для отслеживания количества SQL запросов.
    Использует thread-local storage для хранения счетчика.
    Поддерживает как DEBUG режим (через connection.queries), так и production (через сигналы).
    """
    # Инициализируем счетчик в thread-local storage
    _sql_query_counters.count = 0

    # Пробуем использовать connection.queries (работает только в DEBUG режиме)
    force_debug_cursor_old = connection.force_debug_cursor
    connection.force_debug_cursor = True
    initial_queries_count = len(connection.queries)

    try:
        yield
    finally:
        final_queries_count = len(connection.queries)
        _sql_query_counters.count = final_queries_count - initial_queries_count
        connection.force_debug_cursor = force_debug_cursor_old


def get_sql_queries_count() -> int:
    """
    Возвращает количество SQL запросов, выполненных в текущем контексте.
    """
    return getattr(_sql_query_counters, "count", 0)
