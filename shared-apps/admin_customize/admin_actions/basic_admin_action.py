from abc import ABC

from admin_customize.admin.utils import log_change
from django.contrib import messages
from django.db.models import Model
from django.http import HttpRequest


class BasicAdminActionProcessor(ABC):
    """
    This class is responsible for handling admin actions.
    """

    def __init__(self, request: 'HttpRequest', instance: 'Model') -> None:
        self.request = request
        self.instance = instance

    def process(self) -> None:
        raise NotImplementedError("Subclasses must implement this method.")

    def log_change(self, message_text: str) -> None:
        log_change(self.request.user.id, self.instance, message_text)

    def message_user(self, message_text: str, message_level: int = messages.SUCCESS) -> None:
        """
        This method is used to send a message to the user.
        """
        messages.add_message(
            request=self.request,
            level=message_level,
            message=message_text,
        )
