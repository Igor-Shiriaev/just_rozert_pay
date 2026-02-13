"""
Template context processors for rozert_pay project.
"""

from django.conf import settings
from django.http import HttpRequest


def environment_context(request: HttpRequest) -> dict[str, bool]:
    """
    Add environment-related variables to template context.

    Returns:
        dict with IS_PRODUCTION flag
    """
    return {
        "IS_PRODUCTION": settings.IS_PRODUCTION,
    }
