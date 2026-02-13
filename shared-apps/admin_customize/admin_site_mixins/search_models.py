from typing import TYPE_CHECKING

from admin_customize.admin_site import BetmasterAdminSite, Media

if TYPE_CHECKING:
    from django.core.handlers.wsgi import WSGIRequest
    from django.http import HttpRequest


class SearchModelsAdminSiteMixin(BetmasterAdminSite):
    @property
    def media(self) -> Media:
        return super().media + Media(
            css={'all': ('admin/css/_search_models/search_models.css',)},
        )

    def each_context(self, request: 'WSGIRequest') -> dict:
        return {
            **super().each_context(request),
            'apps_search_data': self._make_apps_data(request),
        }

    def _make_apps_data(self, request: 'HttpRequest') -> list[dict]:
        apps_data = []
        available_apps = self.get_app_list(request)
        for app in available_apps:
            for model in app['models']:
                apps_data.append(
                    {
                        'app': app['app_label'],
                        'model': model['object_name'],
                        'verbose_name': model['name'],
                        'admin_url': model['admin_url'],
                    }
                )
        return apps_data
