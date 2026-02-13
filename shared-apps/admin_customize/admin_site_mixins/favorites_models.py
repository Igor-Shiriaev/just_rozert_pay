import dataclasses
from typing import TYPE_CHECKING, Optional

from django.forms import Media
from django.template.response import TemplateResponse

from admin_customize.admin_site import BetmasterAdminSite

if TYPE_CHECKING:
    from betmaster.models import User
    from django.http import HttpRequest, HttpResponse


@dataclasses.dataclass
class FavoriteAdmin:
    app_label: str
    object_name: str
    verbose_name: str
    admin_url: str


class FavoritesAdminSiteMixin(BetmasterAdminSite):
    @property
    def media(self) -> Media:
        return super().media + Media(
            css={'all': ('admin/css/_favorites/favorites.css',)},
        )

    def _get_favorites(
        self, request: 'HttpRequest', app_label: Optional[str] = None
    ) -> list[FavoriteAdmin]:
        favorite_models = self.__get_favorites(request.user)

        favorites = []
        _available_apps = self.get_app_list(request)
        if app_label is None:
            available_apps = _available_apps
        else:
            available_apps = list(filter(lambda x: x['app_label'] == app_label, _available_apps))

        for app in available_apps:
            for model in app['models']:
                if model['object_name'] in favorite_models:
                    favorites.append(
                        FavoriteAdmin(
                            app_label=app['app_label'],
                            object_name=model['object_name'],
                            verbose_name=model['name'],
                            admin_url=model['admin_url'],
                        )
                    )
        favorites.sort(key=lambda x: favorite_models.index(x.object_name))
        return favorites

    def index(
        self,
        request: 'HttpRequest',
        extra_context: Optional[dict] = None,
    ) -> 'HttpResponse':
        extra_context = extra_context or {}
        extra_context.update(
            {
                'use_favorites': True,
                'collapse_models': bool(self.__get_favorites(request.user)),
                'favorite_models': self._get_favorites(request),
                'user_favorite_models': self.__get_favorites(request.user),
            }
        )
        return super().index(request, extra_context)

    def app_index(
        self,
        request: 'HttpRequest',
        app_label: str,
        extra_context: Optional[dict] = None,
    ) -> 'HttpResponse':
        extra_context = extra_context or {}
        extra_context.update(
            {
                'use_favorites': True,
                'collapse_models': False,
                'favorite_models': self._get_favorites(request, app_label),
                'user_favorite_models': self.__get_favorites(request.user),
            }
        )
        return super().app_index(request, app_label, extra_context)

    def favorites_add(self, request: 'HttpRequest', model_name: str) -> 'HttpResponse':
        favorite_models = self.__get_favorites(request.user)
        if model_name not in favorite_models:
            favorite_models.append(model_name)
        self.__set_favorites(request.user, favorite_models)
        return TemplateResponse(
            request,
            'admin/_favorites/_favorites_star_to_remove.html',
            {'model': {'object_name': model_name}},
            headers={'HX-Trigger': 'update-favorites'},
        )

    def favorites_remove(self, request: 'HttpRequest', model_name: str) -> 'HttpResponse':
        favorite_models = self.__get_favorites(request.user)
        if model_name in favorite_models:
            favorite_models.remove(model_name)
        self.__set_favorites(request.user, favorite_models)

        headers = {'HX-Trigger': 'update-favorites'}
        if not favorite_models:
            headers['HX-Refresh'] = 'true'
        return TemplateResponse(
            request,
            'admin/_favorites/_favorites_star_to_add.html',
            {'model': {'object_name': model_name}},
            headers=headers,
        )

    def __get_favorites(self, user: 'User') -> list[str]:
        if user.is_anonymous:
            return []
        return user.extra.get('favorite_models', [])

    def __set_favorites(self, user: 'User', models: list[str]) -> None:
        if user.is_anonymous:
            return
        user.extra['favorite_models'] = models
        user.save(update_fields=['extra'])

    def favorites_block(self, request: 'HttpRequest') -> 'HttpResponse':
        return TemplateResponse(
            request,
            'admin/_favorites/favorites_block.html',
            {
                'favorite_models': self._get_favorites(request),
            },
        )

    def get_urls(self) -> list:
        from django.urls import path

        urls = super().get_urls()
        urls = [
            path(
                'favorites/add/<model_name>/',
                self.admin_view(self.favorites_add),
                name='favorites_add',
            ),
            path(
                'favorites/remove/<model_name>/',
                self.admin_view(self.favorites_remove),
                name='favorites_remove',
            ),
            path(
                'favorites/',
                self.admin_view(self.favorites_block),
                name='favorites_block',
            ),
            *urls,
        ]
        return urls
