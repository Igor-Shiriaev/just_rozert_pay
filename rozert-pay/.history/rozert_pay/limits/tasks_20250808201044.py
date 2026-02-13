import logging

from celery import Task
from rozert_pay.celery_app import app
from rozert_pay.common import slack
from rozert_pay.common.const import CeleryQueue, EventType
from rozert_pay.limits.models import LimitAlert
from rozert_pay.payment.services.event_logs import create_transaction_log
from slack_sdk.errors import SlackClientError

logger = logging.getLogger(__name__)


@app.task(bind=True, queue=CeleryQueue.LOW_PRIORITY)
def notify_in_slack(
    self: Task, message: str, channel: str, alert_ids: list[int],
) -> None:
    logger.info(f"Sending Slack notification", extra={
        "channel": channel,
        "message": message,
        "alert_ids": alert_ids,
    })
    try:
        slack.slack_client.send_message(channel=channel, text=message)
    except SlackClientError:  # pragma: no cover
        raise self.retry(countdown=10, max_retries=3)

    LimitAlert.objects.filter(id__in=alert_ids).update(is_notified=True)
    for alert_id in alert_ids:
        alert = LimitAlert.objects.get(id=alert_id)
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
