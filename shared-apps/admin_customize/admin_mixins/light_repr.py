from typing import TYPE_CHECKING, Iterable, Optional, Any
from urllib.parse import parse_qsl, urlparse

from django import forms

from admin_customize.admin import BaseModelAdmin
from django.template.response import TemplateResponse

from django.urls import path

from admin_customize.utils import add_param_to_url

if TYPE_CHECKING:
    from django.contrib.admin.views.main import ChangeList
    from django.http import HttpRequest, HttpResponse


class SearchForm(forms.Form):
    q = forms.CharField(
        label='Search',
        required=False,
        widget=forms.TextInput(
            attrs={
                'placeholder': 'Search',
                'class': 'form-control',
            }
        ),
    )


class LightReprMixin(BaseModelAdmin):
    light_table_list_display: Optional[list[str]] = None
    light_table_list_display_links: Optional[list[str]] = None
    light_table_list_per_page: Optional[int] = None
    light_table_search_enabled: bool = True

    def get_urls(self) -> list:
        urls = super().get_urls()
        additional_urls = [
            path(
                'light_table/',
                self.admin_site.admin_view(self.light_table_view),
                name='%s_%s_light_table'
                % (self.model._meta.app_label, self.model._meta.model_name),
            ),
        ]
        return [*additional_urls, *urls]

    def get_initial_url(self, path: str) -> str:
        base_url = self.reverse_admin_url(
            '%s_%s_light_table' % (self.model._meta.app_label, self.model._meta.model_name)
        )
        query_params = dict(parse_qsl(urlparse(path).query))
        related_params = {
            k.split(f'{self.model_name}_')[1]: v
            for k, v in query_params.items()
            if k.startswith(f'{self.model_name}_')
        }
        return add_param_to_url(base_url, add=related_params)

    def light_table_view(
        self, request: 'HttpRequest', extra_context: Optional[dict] = None
    ) -> 'HttpResponse':
        cl = self.get_light_table_changelist_instance(request)
        opts = self.model._meta
        cl.formset = None

        predefined_params = self._get_predefined_params(request)

        search_form = SearchForm(
            request.GET or None,
            initial={'q': predefined_params.get('q')},
        )

        context = {
            **self.admin_site.each_context(request),
            'module_name': str(opts.verbose_name_plural),
            'title': cl.title,
            'subtitle': None,
            'is_popup': cl.is_popup,
            'to_field': cl.to_field,
            'cl': cl,
            'media': self.media,
            'has_add_permission': self.has_add_permission(request),
            'opts': cl.opts,
            'actions_on_top': self.actions_on_top,
            'actions_on_bottom': self.actions_on_bottom,
            'actions_selection_counter': self.actions_selection_counter,
            'preserved_filters': self.get_preserved_filters(request),
            'pages': {
                'is_start': cl.page_num == 1,
                'current': cl.page_num,
                'first_page_url': add_param_to_url(request.get_full_path(), remove=['p']),
                'previous_page_url': add_param_to_url(
                    request.get_full_path(), add={'p': cl.page_num - 1}
                ),
                'next_page_url': add_param_to_url(
                    request.get_full_path(), add={'p': cl.page_num + 1}
                ),
            },
            'search_form': search_form,
            'partial_data_url': 'admin:%s_%s_light_table' % (opts.app_label, opts.model_name),
            'view_all_url': 'admin:%s_%s_changelist' % (opts.app_label, opts.model_name),
            **(extra_context or {}),
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(
            request,
            'admin/light_table.html',
            context,
            headers=self._make_push_url_header(request),
        )

    def _get_predefined_params(self, request: 'HttpRequest') -> dict:
        referer = request.META.get('HTTP_REFERER', '')
        if not referer:
            return {}
        referer_get_params = dict(parse_qsl(urlparse(referer).query))
        related_params = {
            k.split(f'{self.model_name}_')[1]: v
            for k, v in referer_get_params.items()
            if k.startswith(f'{self.model_name}_')
        }
        return related_params

    @property
    def model_name(self) -> str:
        return self.model._meta.model_name.lower()

    def _make_push_url_header(self, request: 'HttpRequest') -> dict:
        keys: list[tuple[str, list[Any]]] = [('q', ['', None]), ('p', ['1', 1])]
        field_to_remove: list[str] = []
        field_to_add: dict[str, str] = {}
        for key, defaults in keys:
            value = request.GET.get(key)
            if all([key in request.GET, bool(value), value not in defaults]):
                field_to_add[f'{self.model_name}_{key}'] = request.GET.get(key)
            else:
                field_to_remove.append(f'{self.model_name}_{key}')

        return {
            'HX-Push-Url': add_param_to_url(
                request.META.get('HTTP_REFERER', ''), add=field_to_add, remove=field_to_remove
            ),
        }

    def get_light_table_changelist_instance(self, request: 'HttpRequest') -> 'ChangeList':
        list_display = self.get_light_table_list_display(request)
        list_display_links = self.get_light_table_list_display_links(request, list_display)
        ChangeList = self.get_changelist(request)
        return ChangeList(
            request=request,
            model=self.model,
            list_display=list_display,
            list_display_links=list_display_links,
            list_filter=[],
            date_hierarchy=[],
            search_fields=[],
            list_select_related=self.get_list_select_related(request),
            list_per_page=self.get_light_table_list_per_page(),
            list_max_show_all=self.list_max_show_all,
            list_editable=[],
            model_admin=self,
            sortable_by=[],
            search_help_text='',
        )

    def get_light_table_list_display(self, request: 'HttpRequest') -> list[str]:
        return self.light_table_list_display or self.get_list_display(request)

    def get_light_table_list_display_links(
        self, request: 'HttpRequest', list_display: Iterable[str]
    ) -> list[str]:
        return self.light_table_list_display_links or self.get_list_display_links(
            request, list_display
        )

    def get_light_table_list_per_page(self) -> int:
        return self.light_table_list_per_page or self.list_per_page
