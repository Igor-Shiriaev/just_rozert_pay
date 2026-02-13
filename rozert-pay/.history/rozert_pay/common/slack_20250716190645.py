import logging

from django.conf import settings
from slack_sdk import WebClient
from slack_sdk.base_client import SlackResponse
from .slack_sdk.web/slack_response.py import SlackResponse
from slack_sdk.errors import SlackClientError

logger = logging.getLogger(__name__)


class SlackClient:
    _client: WebClient

    def __init__(self) -> None:
        self._client = WebClient(token=settings.SLACK_TOKEN)

    def send_message(self, channel: str, text: str) -> None:  # pragma: no cover
        try:
            response: SlackResponse = self._client.chat_postMessage(channel=channel, text=text)
            logger.info(
                "Slack message sent successfully",
                extra={"channel": channel, "ts": response.get("ts")},
            )
        except SlackClientError:
            logger.exception("Failed to send Slack message", extra={"channel": channel})
            raise
        except Exception:
            logger.exception(
                "Unexpected error sending Slack message", extra={"channel": channel}
            )
            raise


slack_client = SlackClient()
