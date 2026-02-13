import logging
from threading import local
from typing import TYPE_CHECKING, Dict, Optional

from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin
import logging

if TYPE_CHECKING:
    from betmaster.common_models import User

_thread_locals = local()


def get_current_request() -> HttpRequest:
    """returns the request object for this thread"""
    return getattr(_thread_locals, 'request', None)


def get_current_request_signin_event_id() -> Optional[int]:
    current_request = get_current_request()
    if not current_request:
        return None
    try:
        return current_request.session.get('signin_event_id')
    except Exception:
        logging.getLogger(__name__).exception("Error in get_current_request_signin_event_id")
        return None

def get_current_user() -> Optional['User']:
    """returns the current user, if exist, otherwise returns None"""
    request = get_current_request()
    if request:
        return getattr(request, 'user', None)
    return None


def get_thread_cache() -> Optional[Dict]:
    """Returns cache for this thread"""
    return getattr(_thread_locals, 'cache', None)


class ThreadLocalMiddleware(MiddlewareMixin):
    def process_request(self, request):  # type: ignore
        _thread_locals.request = request
        _thread_locals.cache = {}

    def process_response(self, request, response):  # type: ignore
        for attr_name in ('request', 'cache'):
            if hasattr(_thread_locals, attr_name):
                delattr(_thread_locals, attr_name)
        return response
