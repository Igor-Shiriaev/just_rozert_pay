from typing import TYPE_CHECKING, TypedDict, Optional

from django.forms import Media

from admin_customize.admin_site import BetmasterAdminSite

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

LightTableData = TypedDict(
    'LightTableData',
    {
        'title': str,
        'initial_url': str,
    },
)


class DashboardTablesAdminSiteMixin(BetmasterAdminSite):
    dashboard_table_models: list[str] = []

    @property
    def media(self) -> Media:
        media = super().media
        media += Media(
            css={
                'all': (
                    'admin/css/changelists.css',
                    'admin/css/_dashboard/dashboard.css',
                ),
            }
        )
        return media

    def get_dashboard_tables(self, request: 'HttpRequest') -> list[LightTableData]:
        required_admin_sites = []
        for model_admin in self._registry.values():
            permission_name = f'{model_admin.opts.app_label}.view_{model_admin.opts.model_name}'
            if (
                model_admin.opts.object_name in self.dashboard_table_models
                and request.user.has_perm(permission_name)
            ):
                required_admin_sites.append(model_admin)

        return [
            LightTableData(
                title=model_admin.opts.verbose_name_plural,
                initial_url=model_admin.get_initial_url(request.get_full_path()),
            )
            for model_admin in required_admin_sites
        ]

    def index(self, request: 'HttpRequest', extra_context: Optional[dict]=None) -> 'HttpResponse':
        extra_context = extra_context or {}
        extra_context.update(
            {
                'dashboard_tables': self.get_dashboard_tables(request),
            }
        )
        return super().index(request, extra_context=extra_context)
