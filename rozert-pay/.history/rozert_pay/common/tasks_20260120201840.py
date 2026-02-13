import logging
import re
from urllib.parse import urlparse

import requests
from django.conf import settings
from rozert_pay.celery_app import app
from rozert_pay.common import metrics
from rozert_pay.common.const import CeleryQueue

logger = logging.getLogger(__name__)


def _get_broker_vhost() -> str:
    # Try to get vhost from CELERY_BROKER_URL path
    try:
        parsed = urlparse(settings.CELERY_BROKER_URL)
        # For amqp urls a path like //vhost or /vhost is possible.
        # Normalize: strip leading slashes, default to "/" if empty.
        path = parsed.path or ""
        # Some libs use double-slash before vhost, collapse to single semantic
        path = re.sub(r"^/+", "/", path)
        vhost = path.lstrip("/")
        return vhost or "/"
    except Exception:
        return "/"


@app.task(name="common.collect_rabbit_queues_metrics", queue=CeleryQueue.SERVICE)
def collect_rabbit_queues_metrics() -> None:
    scheme = getattr(settings, "RABBITMQ_MANAGEMENT_SCHEME", "http")
    port = int(getattr(settings, "RABBITMQ_MANAGEMENT_PORT", 15672))
    host = getattr(settings, "RABBITMQ_HOST", "localhost")
    user = getattr(settings, "RABBITMQ_USER", "guest")
    password = getattr(settings, "RABBITMQ_PASSWORD", "guest")

    url = f"{scheme}://{host}:{port}/api/queues"

<<<<<<< HEAD
    resp = requests.get(url, auth=(user, password), timeout=5)
    resp.raise_for_status()
    queues = resp.json()

    if not queues:
        logger.warning("No queues found to collect metrics!")
=======
    try:
        resp = requests.get(url, auth=(user, password), timeout=5)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Failed to fetch RabbitMQ queues metrics: %s", e, exc_info=True)
>>>>>>> origin/igorshiryaev/sc-282862/worldpay-add-3ds-support-2
        return

    queues = resp.json()

    if not queues:
        logger.warning("No queues found to collect metrics!")
        return

    target_vhost = _get_broker_vhost()

    for q in queues:
        q_name = q.get("name", "")
        q_vhost = q.get("vhost", "")

<<<<<<< HEAD
        messages = int(q.get("messages", 0) or 0)
        consumers = int(q.get("consumers", 0) or 0)
        messages_unack = int(q.get("messages_unacknowledged", 0) or 0)
        messages_ready = int(q.get("messages_ready", 0) or 0)

=======
        # Only collect metrics for queues in the target vhost
        if q_vhost != target_vhost:
            continue

        messages = int(q.get("messages", 0) or 0)
        consumers = int(q.get("consumers", 0) or 0)
        messages_unack = int(q.get("messages_unacknowledged", 0) or 0)
        messages_ready = int(q.get("messages_ready", 0) or 0)

>>>>>>> origin/igorshiryaev/sc-282862/worldpay-add-3ds-support-2
        metrics.RABBIT_QUEUE_MESSAGES.labels(queue=q_name, vhost=q_vhost).set(messages)
        metrics.RABBIT_QUEUE_CONSUMERS.labels(queue=q_name, vhost=q_vhost).set(
            consumers
        )
        metrics.RABBIT_QUEUE_MESSAGES_UNACKED.labels(queue=q_name, vhost=q_vhost).set(
            messages_unack
        )
        metrics.RABBIT_QUEUE_MESSAGES_READY.labels(queue=q_name, vhost=q_vhost).set(
            messages_ready
        )
        logger.info(
            "Published metrics",
            extra={
                "messages": messages,
                "consumers": consumers,
                "messages_unack": messages_unack,
                "messages_ready": messages_ready,
                "queue": q_name,
                "vhost": q_vhost,
            },
        )
