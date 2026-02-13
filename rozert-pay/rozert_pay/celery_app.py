import logging
import os
import threading
import time
from uuid import uuid4

from bm.django_utils.middleware import get_request_id, set_request_id
from bm.logging import set_global_logging_context
from celery import Celery
from celery.schedules import crontab
from celery.signals import (
    after_task_publish,
    before_task_publish,
    setup_logging,
    task_failure,
    task_prerun,
    task_success,
)
from flask import Flask, Response
from kombu import Queue  # type: ignore[import]
from prometheus_client import generate_latest
from rozert_pay.common import metrics
from rozert_pay.common.const import CeleryQueue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rozert_pay.settings")

app = Celery("rozert_pay")
app.conf.task_queues = [Queue(q) for q in CeleryQueue]

app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# periodic tasks
app.conf.beat_schedule = {
    "check_pending_transaction_status": {
        "task": "rozert_pay.payment.tasks.check_pending_transaction_status",
        "schedule": crontab(minute="*/1"),
    },
    "check_bitso_spei_bank_codes": {
        "task": "rozert_pay.payment.tasks.check_bitso_spei_bank_codes",
        "schedule": crontab(hour="7", minute="55", day_of_week="1"),
    },
    "sync_muwe_spei_bank_list": {
        "task": "rozert_pay.payment.systems.muwe_spei.tasks.sync_muwe_spei_bank_list",
        "schedule": crontab(hour="3", minute="0"),  # Daily at 3:00 AM
    },
    "collect_rabbit_queues_metrics": {
        "task": "common.collect_rabbit_queues_metrics",
        "schedule": crontab(minute="*/1"),
    },
    # Сommented before release just in case
    # "cleanup_duplicate_event_logs": {
    #     "task": "rozert_pay.payment.tasks.cleanup_duplicate_logs",
    #     "schedule": crontab(minute="0", hour="*/2"),
    #     "kwargs": {"is_dry_run": False},
    # },
}


logger = logging.getLogger(__name__)


@setup_logging.connect
def disable_celery_logging(**kwargs):  # type: ignore[no-untyped-def] # pragma: no cover
    pass


@before_task_publish.connect
def before_task_publish_handler(headers, body, **kw):  # type: ignore[no-untyped-def] # pragma: no cover
    request_id = get_request_id()
    if not request_id:
        logger.warning(
            "request_id is not set!",
            extra={
                "headers": headers,
                "body": body,
                "kw": kw,
            },
        )
        return

    body[1]["request_id"] = request_id


@after_task_publish.connect
def after_task_publish_handler(**kwargs):  # type: ignore[no-untyped-def] # pragma: no cover
    logger.info(
        "published celery task",
        extra={
            "routing": kwargs.get("routing_key"),
            "sender": kwargs.get("sender"),
            "body": str(kwargs.get("body")),
        },
    )


@task_prerun.connect
def before_task_run(task, kwargs, **kw):  # type: ignore[no-untyped-def] # pragma: no cover
    task = kw.get("sender")
    task._started_at = time.time()

    # Инициализируем контекстный менеджер для отслеживания SQL запросов
    task._sql_queries_context = metrics.track_sql_queries()
    task._sql_queries_context.__enter__()

    request_id = kwargs.pop("request_id", None) or get_request_id()
    if not request_id:
        logger.warning(
            "request_id is not set! Use fake one",
            extra={
                "kwargs": kwargs,
                "kw": kw,
            },
        )
        request_id = f"celery:{uuid4()}"

    set_request_id(request_id)
    set_global_logging_context(request_id=request_id)

    try:
        queue = task.request.delivery_info.get("routing_key") if task else None
    except Exception:
        queue = None

    # Log task start with minimal, safe context
    args_preview = kw.get("args")
    if args_preview is not None:
        args_preview = repr(args_preview)
        if len(args_preview) > 300:
            args_preview = args_preview[:300] + "..."

    kwargs_preview = kwargs
    if kwargs_preview is not None:
        kwargs_preview = dict(kwargs_preview)
        # don't log request_id again
        kwargs_preview.pop("request_id", None)
        kwargs_preview = repr(kwargs_preview)
        if len(kwargs_preview) > 300:
            kwargs_preview = kwargs_preview[:300] + "..."

    logger.info(
        "task started",
        extra={
            "task_name": task.name if task else None,
            "task_id": kw.get("task_id"),
            "queue": queue,
            "args_data": args_preview,
            "kwargs_data": kwargs_preview,
        },
    )


@task_success.connect
def on_task_success(sender, **kw):  # type: ignore[no-untyped-def] # pragma: no cover
    queue = sender.request.delivery_info.get("routing_key")
    duration = time.time() - sender._started_at

    # Завершаем контекстный менеджер для SQL запросов
    sql_queries_count = 0
    if hasattr(sender, "_sql_queries_context"):
        try:
            sender._sql_queries_context.__exit__(None, None, None)
            sql_queries_count = metrics.get_sql_queries_count()
        except Exception:
            logger.exception("Error closing SQL queries context")

    metrics.TASKS_COUNT.labels(
        task_name=sender.name,
        status="success",
        queue=queue,
        exception=None,
    ).inc()
    metrics.TASK_DURATION.labels(
        task_name=sender.name,
        status="success",
        queue=queue,
        exception=None,
    ).observe(duration)
    metrics.TASK_SQL_QUERIES.labels(
        task_name=sender.name,
        status="success",
        queue=queue,
        exception=None,
    ).observe(sql_queries_count)


@task_failure.connect
def log_task_failure(  # type: ignore[no-untyped-def] # pragma: no cover
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **kw,
):
    queue = sender.request.delivery_info.get("routing_key")
    duration = time.time() - sender._started_at

    # Завершаем контекстный менеджер для SQL запросов
    sql_queries_count = 0
    if hasattr(sender, "_sql_queries_context"):
        try:
            sender._sql_queries_context.__exit__(None, None, None)
            sql_queries_count = metrics.get_sql_queries_count()
        except Exception:
            logger.exception("Error closing SQL queries context")

    logger.exception(
        f"error in task {sender}",
        exc_info=True,
        extra={
            "task_id": task_id,
            "exception": exception,
            "task_args": args,
            "task_kwargs": kwargs,
            "traceback": traceback,
            "einfo": einfo,
            "queue": queue,
            "duration": duration,
        },
    )

    exception_class = exception.__class__.__name__ if exception else None
    metrics.TASKS_COUNT.labels(
        task_name=sender.name,
        status="failed",
        queue=queue,
        exception=exception_class,
    ).inc()
    metrics.TASK_DURATION.labels(
        task_name=sender.name,
        status="failed",
        queue=sender.request.delivery_info.get("routing_key"),
        exception=exception_class,
    ).observe(duration)
    metrics.TASK_SQL_QUERIES.labels(
        task_name=sender.name,
        status="failed",
        queue=queue,
        exception=exception_class,
    ).observe(sql_queries_count)


# Expose metrics via HTTP to be collected via prometheus
metrics_app = Flask("celery_metrics")


@metrics_app.route("/metrics")
def metrics_view() -> Response:
    return Response(generate_latest(metrics.prometheus_registry), mimetype="text/plain")


class MetricsThread(threading.Thread):
    def run(self) -> None:
        logger.info("Run celery metrics")
        metrics_app.run(host="0.0.0.0", port=5200)


if os.environ.get("CELERY_METRICS"):
    metrics_thread = MetricsThread()
    metrics_thread.daemon = True
    metrics_thread.start()
