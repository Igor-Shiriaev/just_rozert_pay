import json
import logging
from unittest.mock import Mock, patch

import pytest
from rozert_pay.common.slack import SlackClient, slack_client
from slack_sdk.errors import SlackClientError
from slack_sdk.web.client import WebClient
from slack_sdk.web.slack_response import SlackResponse


@pytest.fixture
def mock_settings():
    """Fixture to mock Django settings with SLACK_TOKEN."""
    with patch("rozert_pay.common.slack.settings") as mock_settings:
        mock_settings.SLACK_TOKEN = "test-token"
        yield mock_settings


@pytest.fixture
def mock_web_client():
    """Fixture to mock WebClient and return its instance."""
    with patch("rozert_pay.common.slack.WebClient") as mock_web_client:
        mock_client_instance = Mock(spec=WebClient)
        mock_web_client.return_value = mock_client_instance
        yield mock_client_instance


@pytest.fixture
def slack_client_instance(mock_settings, mock_web_client):
    """Fixture to create a SlackClient instance with mocked dependencies."""
    return SlackClient()


class TestSlackClient:
    def test_send_message_success_with_dict_response(
        self, mock_web_client, slack_client_instance, caplog
    ):
        """Test successful message sending with dict response data."""
        mock_response = Mock(spec=SlackResponse)
        mock_response.status_code = 200
        mock_response.data = {"ok": True, "ts": "1234567890.123456"}
        mock_web_client.chat_postMessage.return_value = mock_response

        with caplog.at_level(logging.INFO):
            result = slack_client_instance.send_message("#test-channel", "Test message")

        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="#test-channel", text="Test message"
        )
        assert result is None

        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "INFO"
        assert log_record.message_to_send == "Test message"
        assert log_record.channel == "#test-channel"
        assert log_record.response == {"ok": True, "ts": "1234567890.123456"}

    def test_send_message_success_with_json_string_response(
        self, mock_web_client, slack_client_instance, caplog
    ):
        """Test successful message sending with JSON string response data."""
        mock_response = Mock(spec=SlackResponse)
        mock_response.status_code = 200
        response_data = {"ok": True, "ts": "1234567890.123456"}
        mock_response.data = json.dumps(response_data)
        mock_web_client.chat_postMessage.return_value = mock_response

        with caplog.at_level(logging.INFO):
            result = slack_client_instance.send_message("#test-channel", "Test message")

        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="#test-channel", text="Test message"
        )
        assert result is None

        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "INFO"
        assert log_record.message_to_send == "Test message"
        assert log_record.channel == "#test-channel"
        assert log_record.response == response_data

    def test_send_message_non_200_status_code(
        self, mock_web_client, slack_client_instance, caplog, disable_error_logs
    ):
        """Test handling of non-200 status code response."""
        mock_response = Mock(spec=SlackResponse)
        mock_response.status_code = 400
        mock_response.data = {
            "ok": False,
            "error": "channel_not_found",
            "detail": "Value passed for channel was invalid.",
        }
        mock_web_client.chat_postMessage.return_value = mock_response

        with caplog.at_level(logging.ERROR):
            result = slack_client_instance.send_message(
                "#invalid-channel", "Test message"
            )

        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="#invalid-channel", text="Test message"
        )
        assert result is None

        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "ERROR"
        assert log_record.message_to_send == "Test message"
        assert log_record.channel == "#invalid-channel"
        assert log_record.status_code == 400
        assert log_record.response == {
            "ok": False,
            "error": "channel_not_found",
            "detail": "Value passed for channel was invalid.",
        }

    def test_send_message_slack_client_error(
        self, mock_web_client, slack_client_instance, caplog, disable_error_logs
    ):
        """Test SlackClientError handling with proper logging and re-raising."""
        slack_error = SlackClientError("Slack API error")
        mock_web_client.chat_postMessage.side_effect = slack_error

        with caplog.at_level(logging.ERROR):
            with pytest.raises(SlackClientError):
                slack_client_instance.send_message("#test-channel", "Test message")

        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "ERROR"
        assert log_record.message == "Failed to send Slack message"
        assert log_record.channel == "#test-channel"

    def test_send_message_unexpected_error(
        self,
        mock_web_client,
        slack_client_instance,
        caplog,
    ):
        """Test unexpected error handling with proper logging and re-raising."""
        unexpected_error = ValueError("Unexpected error")
        mock_web_client.chat_postMessage.side_effect = unexpected_error

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError):
                slack_client_instance.send_message("#test-channel", "Test message")

        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "ERROR"
        assert log_record.message == "Unexpected error sending Slack message"
        assert log_record.channel == "#test-channel"

    def test_send_message_status_200_with_error_response(
        self, mock_web_client, slack_client_instance, caplog
    ):
        """Test handling of 200 status code but with error in response body."""
        mock_response = Mock(spec=SlackResponse)
        mock_response.status_code = 200
        mock_response.data = {
            "ok": False,
            "error": "invalid_auth",
            "detail": "Invalid token.",
        }
        mock_web_client.chat_postMessage.return_value = mock_response

        with caplog.at_level(logging.INFO):
            result = slack_client_instance.send_message("#test-channel", "Test message")

        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="#test-channel", text="Test message"
        )
        assert result is None

        # Check logging - should be INFO even though response contains error
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "INFO"
        assert log_record.message_to_send == "Test message"
        assert log_record.channel == "#test-channel"
        assert log_record.response == {
            "ok": False,
            "error": "invalid_auth",
            "detail": "Invalid token.",
        }

    def test_send_message_malformed_json_response(
        self, mock_web_client, slack_client_instance
    ):
        """Test handling of malformed JSON response data."""
        mock_response = Mock(spec=SlackResponse)
        mock_response.status_code = 200
        mock_response.data = '{"ok": true, "ts": "invalid_json"'  # Malformed JSON
        mock_web_client.chat_postMessage.return_value = mock_response

        # Execute & Verify - should raise JSONDecodeError
        with pytest.raises(json.JSONDecodeError):
            slack_client_instance.send_message("#test-channel", "Test message")

    def test_slack_client_singleton_instance(self):
        """Test that slack_client singleton instance exists and is a SlackClient."""
        assert isinstance(slack_client, SlackClient)
        assert hasattr(slack_client, "_client")
        assert hasattr(slack_client, "send_message")
