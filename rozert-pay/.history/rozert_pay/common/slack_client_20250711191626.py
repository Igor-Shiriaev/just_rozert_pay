import logging
from typing import Optional

from django.conf import settings
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackClient:
    """Slack client using the Slack Python SDK for sending messages to channels."""
    
    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or getattr(settings, 'SLACK_BOT_TOKEN', None)
        self._client: Optional[WebClient] = None
    
    @property
    def client(self) -> WebClient:
        if self._client is None:
            if not self.token:
                raise ValueError("Slack bot token is not configured")
            self._client = WebClient(token=self.token)
        return self._client
    
    def send_message(self, channel: str, text: str) -> bool:
        """
        Send a message to a Slack channel.
        
        Args:
            channel: Slack channel name (with or without #)
            text: Message text to send
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        if not self.token:
            logger.warning(
                "Slack bot token not configured, skipping message send",
                extra={"channel": channel, "text": text}
            )
            if settings.DEBUG:
                logger.debug(f"Would send to {channel}: {text}")
            return False
        
        # Ensure channel starts with #
        if not channel.startswith('#'):
            channel = f"#{channel}"
        
        try:
            response = self.client.chat_postMessage(
                channel=channel,
                text=text
            )
            logger.info(
                "Slack message sent successfully",
                extra={"channel": channel, "ts": response.get("ts")}
            )
            return True
        except SlackApiError as e:
            logger.error(
                "Failed to send Slack message",
                extra={
                    "channel": channel,
                    "error": str(e),
                    "status_code": e.response.status_code if e.response else None
                }
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error sending Slack message",
                extra={"channel": channel, "error": str(e)}
            )
            return False


# Global instance for easy usage
slack_client = SlackClient() 