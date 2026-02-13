import logging

from celery import Task
from rozert_pay.celery_app import app
from rozert_pay.common import slack
from rozert_pay.common.const import CeleryQueue, EventType
from rozert_pay.limits.models import LimitAlert
from rozert_pay.payment.services.event_logs import create_event_log, create_transaction_log
from slack_sdk.errors import SlackClientError

logger = logging.getLogger(__name__)


@app.task(bind=True, queue=CeleryQueue.LOW_PRIORITY)
def notify_in_slack(
    self: Task,  # type: ignore[type-arg]
    message: str,
    channel: str,
    alert_ids: list[int],
) -> None:
    pending_ids: list[int] = list(
        LimitAlert.objects.filter(id__in=alert_ids, is_notified=False).values_list(
            "id", flat=True
        )
    )
    if not pending_ids:
        logger.info(
            "Skipping Slack notification, all alerts already notified",
            extra={
                "channel": channel,
                "slack_message": message,
                "alert_ids": alert_ids,
            },
        )
        return

    logger.info(
        "Sending Slack notification",
        extra={
            "channel": channel,
            "slack_message": message,
            "alert_ids": alert_ids,
        },
    )
    try:
        slack.slack_client.send_message(channel=channel, text=message)
    except SlackClientError:  # pragma: no cover
        raise self.retry(countdown=10, max_retries=3)

    LimitAlert.objects.filter(id__in=pending_ids).update(is_notified=True)
    for alert_id in pending_ids:
        alert = LimitAlert.objects.get(id=alert_id)
        create_event_log(
            event_type=EventType.UPDATE_LIMIT,
        )
        create_transaction_log(
            trx_id=alert.transaction.id,
            event_type=EventType.INFO,
            description=f"Slack notification sent for limit alert {alert_id}",
            extra={
                "alert_id": alert_id,
                "channel": channel,
                "message": message,
            },
        )
