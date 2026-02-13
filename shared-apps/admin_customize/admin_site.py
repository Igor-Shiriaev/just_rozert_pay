from typing import List, Optional, Tuple

from admin_customize.admin_views import set_timezone
from django.conf import settings
from django.contrib import admin
from django.core.handlers.wsgi import WSGIRequest
from django.forms import Media
from django.http import HttpRequest, HttpResponse


class BetmasterAdminSite(admin.AdminSite):
    ADDITIONAL_HEADER_LINKS: List[Tuple[str, str]] = []
    enable_nav_sidebar = False
    index_title = 'Dashboard'

    @property
    def media(self) -> Media:
        return Media(
            js=(
                'js/htmx-2.0.4.min.js',
                'js/hyperscript-0.9.14.min.js',
            ),
            css={},
        )

    def get_additional_header_links(self, request: HttpRequest) -> List[Tuple[str, str]]:
        return self.ADDITIONAL_HEADER_LINKS.copy()

    def get_title(self, request: HttpRequest) -> str:
        return self.site_title

    def get_header(self, request: HttpRequest) -> str:
        return self.site_header

    def each_context(self, request: WSGIRequest) -> dict:
        context = super().each_context(request)
        context['site_title'] = self.get_title(request)
        context['site_header'] = self.get_header(request)
        context['additional_header_links'] = self.get_additional_header_links(request)
        context['admin_site_media'] = self.media
        context['ENV_NAMESPACE'] = getattr(settings, 'ENV_NAMESPACE', None)
        if request.user.is_authenticated:
            context['current_timezone'] = getattr(request.user, 'extra', {}).get('timezone', settings.TIME_ZONE)
        else:
            context['current_timezone'] = settings.TIME_ZONE
        return context

    def login(self, request: WSGIRequest, extra_context: Optional[dict] = None) -> HttpResponse:
        response = super().login(request, extra_context)
        if request.user.is_authenticated:
            if user_timezone := getattr(request.user, 'extra', {}).get('timezone'):
                request.session['django_timezone'] = user_timezone
        return response

    def logout(self, request: WSGIRequest, extra_context: Optional[dict] = None) -> HttpResponse:  # type: ignore
        response = super().logout(request, extra_context)
        if 'django_timezone' in request.session:
            del request.session['django_timezone']
        return response

    def get_urls(self) -> list:
        from django.urls import path

        urls = [
            path(
                'set_timezone/',
                self.admin_view(set_timezone),
                name='set_timezone',
            ),
            *super().get_urls(),
        ]
        return urls
