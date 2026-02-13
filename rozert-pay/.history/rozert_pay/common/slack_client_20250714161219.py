import logging
from typing import Optional

from django.conf import settings
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackClient:
    def __init__(self) -> None:
        self.client: WebClient = WebClient(token=settings.SLACK_TOKEN)

    def send_message(self, channel: str, text: str) -> bool:
        # Ensure channel starts with #
        if not channel.startswith("#"):
            channel = f"#{channel}"

        try:
            response = self.client.chat_postMessage(channel=channel, text=text)
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
