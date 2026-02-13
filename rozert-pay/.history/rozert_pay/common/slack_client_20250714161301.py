import logging

from django.conf import settings
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackClient:
    _client
    def __init__(self) -> None:
        self._client: WebClient = WebClient(token=settings.SLACK_TOKEN)

    def send_message(self, channel: str, text: str) -> bool:
        try:
            response = self._client.chat_postMessage(channel=channel, text=text)
            logger.info(
                "Slack message sent successfully",
                extra={"channel": channel, "ts": response.get("ts")},
            )
            return True
        except SlackApiError:
            logger.exception(
                "Failed to send Slack message",
                extra={"channel": channel},
            )
            return False
        except Exception:
            logger.exception(
                "Unexpected error sending Slack message",
                extra={"channel": channel},
            )
            return False


slack_client = SlackClient()
