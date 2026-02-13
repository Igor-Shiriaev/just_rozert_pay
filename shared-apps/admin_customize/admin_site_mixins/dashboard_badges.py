from functools import wraps
from typing import Any, Callable, TypedDict, Optional, Dict, TYPE_CHECKING

from django.forms import Media

from admin_customize.admin_site import BetmasterAdminSite
from django.http import HttpRequest, HttpResponse
from django.template import loader
from django.urls import path
from django.utils.safestring import mark_safe

if TYPE_CHECKING:
    from b2b_admin.admin import B2BAdminDashboardStatus

StatusBadgeValue = TypedDict(
    'StatusBadgeValue',
    {
        'name': str,
        'value': Any,
    },
)

StatusBadgeData = TypedDict(
    'StatusBadgeData',
    {
        'title': str,
        'values': list[StatusBadgeValue],
    },
)

StatusBadgesData = TypedDict(
    'StatusBadgesData',
    {
        'title': str,
        'badges': list[StatusBadgeData],
    },
)


StatusBadgeMethod = Callable[['B2BAdminDashboardStatus', HttpRequest], Dict[str, Any]]
StatusBadgeHandler = Callable[['B2BAdminDashboardStatus', HttpRequest], StatusBadgeData]


def status_badge(
    title: str,
) -> Callable[[StatusBadgeMethod], StatusBadgeHandler]:
    def decorator(func: StatusBadgeMethod) -> StatusBadgeHandler:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> StatusBadgeData:
            data = func(*args, **kwargs)
            status_badge_values = [
                StatusBadgeValue(name=name, value=value) for name, value in data.items()
            ]
            return StatusBadgeData(
                title=title,
                values=status_badge_values,
            )

        wrapper.title = title  # type: ignore

        return wrapper  # type: ignore

    return decorator


class DashboardStatusBadgesAdminSiteMixin(BetmasterAdminSite):
    index_page_status_badges: list[tuple[str, list[str]]] = []

    @property
    def media(self) -> Media:
        media = super().media
        media += Media(
            css={
                'all': ('admin/css/_badges/badges.css',),
            },
        )
        return media

    def make_status_badges(self, request: 'HttpRequest') -> list[dict[str, Any]]:
        return [
            {
                'title': title,
                'badges': [
                    self._make_status_badge_placeholder(request, status_badge_name)
                    for status_badge_name in status_badges
                ],
            }
            for title, status_badges in self.index_page_status_badges
        ]

    def _make_status_badge_placeholder(
        self, request: 'HttpRequest', status_badge_name: str
    ) -> str:
        template = loader.get_template('admin/_badges/status_badge_placeholder.html')
        badge_handler = getattr(self, status_badge_name)
        return template.render(
            {
                'status_badge_name': status_badge_name,
                'badge_title': badge_handler.title,
            },
            request=request,
        )

    def index(
        self, request: 'HttpRequest', extra_context: Optional[dict] = None
    ) -> 'HttpResponse':
        extra_context = extra_context or {}
        extra_context.update(
            {
                'status_badges': self.make_status_badges(request),
            }
        )
        return super().index(request, extra_context=extra_context)

    def get_urls(self) -> list:
        urls = super().get_urls()
        urls = [
            path(
                'status-badge/<str:status_badge_name>/',
                self.admin_view(self.get_status_badge_data),
                name='status-badge',
            ),
            *urls,
        ]
        return urls

    def get_status_badge_data(
        self, request: 'HttpRequest', status_badge_name: str
    ) -> 'HttpResponse':
        template = loader.get_template('admin/_badges/status_badge_block.html')
        status_badge_handler: Optional[StatusBadgeHandler] = getattr(
            self, status_badge_name, None
        )  # type: ignore
        if status_badge_handler is None:
            return HttpResponse(status=404)
        try:
            badge_data = template.render({'badge': status_badge_handler(request)}, request=request)  # type: ignore
        except Exception as e:
            badge_data = template.render({'error': str(e)}, request=request)

        return HttpResponse(mark_safe(badge_data))
