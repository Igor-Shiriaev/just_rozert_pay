import logging
import json

from django.conf import settings
from slack_sdk import WebClient
from slack_sdk.web.slack_response import SlackResponse
from slack_sdk.errors import SlackClientError

logger = logging.getLogger(__name__)


class SlackClient:
    _client: WebClient

    def __init__(self) -> None:
        self._client = WebClient(token=settings.SLACK_TOKEN)

    def send_message(self, channel: str, text: str) -> None:
        try:
            response: SlackResponse = self._client.chat_postMessage(channel=channel, text=text)
        except SlackClientError:  # pragma: no cover
            logger.exception("Failed to send Slack message", extra={"channel": channel})
            raise
        except Exception:  # pragma: no cover
            logger.exception(
                "Unexpected error sending Slack message", extra={"channel": channel}
            )
            raise
        response_data = (
            response.data if isinstance(response.data, dict) else json.loads(response.data)
        )
        if response.status_code != 200:
            logger.error(
                "Failed to send Slack message",
                extra={
                    "message_to_send": text,
                    "channel": channel,
                    "status_code": response.status_code,
                    "response": response_data,
                },
            )
            return
        logger.info(
            "Slack message sent successfully",
            extra={"message_to_send": text, "channel": channel, "response": response_data},
        )
        return


slack_client = SlackClient()
