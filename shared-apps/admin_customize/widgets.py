from typing import TYPE_CHECKING, Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlencode

from django import forms
from django.contrib.admin.views.main import TO_FIELD_VAR
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.encoding import force_str

if TYPE_CHECKING:
    from django.contrib.admin import AdminSite
    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.forms.renderers import BaseRenderer


def get_changelist_url(ct: ContentType, admin_site: 'AdminSite') -> str:
    params = {
        TO_FIELD_VAR: ct.model_class()._meta.pk.name,
    }
    url = reverse(f'{admin_site.name}:{ct.app_label}_{ct.model}_changelist', current_app=admin_site.name)
    url += '?' + urlencode(params)
    return url


class GenericForeignKeyRawIdInput(forms.TextInput):
    def __init__(  # type: ignore
        self, gfk_field: 'GenericForeignKey', admin_site: 'AdminSite', attrs: Optional[Dict[str, Any]] = None
    ) -> None:
        self.admin_site = admin_site
        self.gfk_field = gfk_field
        self.model = gfk_field.model
        self.opts = self.model._meta
        if attrs is None:
            attrs = {}
        if 'class' not in attrs:
            attrs['class'] = 'vForeignKeyRawIdAdminField'
        super().__init__(attrs=attrs)

    def get_context(self, name: str, value: Any, attrs: Dict[str, Any]) -> Dict[str, Any]:  # type: ignore
        context = super().get_context(name, value, attrs)
        url = ''
        if value:
            ct = ContentType.objects.get_for_model(value)
            url = get_changelist_url(ct, self.admin_site)
            context['widget']['value'] = self.format_value(value.pk)
        context['widget']['url'] = url
        return context


class GenericForeignKeyRawIdSelect(forms.Select):
    def __init__(  # type: ignore
        self,
        gfk_field: 'GenericForeignKey',
        admin_site: 'AdminSite',
        attrs: Optional[Dict[str, Any]] = None,
        choices: Iterable[Tuple[Any, str]] = (),
    ) -> None:
        self.gfk_field = gfk_field
        self.admin_site = admin_site
        if not choices:
            opts = self.gfk_field.model._meta
            ct_field = opts.get_field(gfk_field.ct_field)
            choices = ct_field.get_choices()

        if attrs is None:
            attrs = {}
        if 'class' not in attrs:
            attrs['class'] = 'vGenericForeignKeyTypeSelect'

        super().__init__(attrs=attrs, choices=choices)

    def create_option(  # type: ignore
        self,
        name: str,
        value: Any,
        label: str,
        selected: bool,
        index: int,
        subindex: Optional[int] = None,
        attrs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value:
            ct = ContentType.objects.get(pk=value)
            url = get_changelist_url(ct, self.admin_site)
            option['attrs']['data-url'] = url
        return option


class GenericForeignKeyRawIdWidget(forms.MultiWidget):
    template_name = 'forms/widgets/generic_foreign_key_field_widget.html'

    def __init__(  # type: ignore
        self, gfk_field: 'GenericForeignKey', admin_site: 'AdminSite', attrs: Optional[Dict[str, Any]] = None
    ) -> None:
        select_widget = GenericForeignKeyRawIdSelect(gfk_field, admin_site, attrs)
        input_widget = GenericForeignKeyRawIdInput(gfk_field, admin_site, attrs)
        widgets = (select_widget, input_widget)
        super().__init__(widgets, attrs)

    def render(  # type: ignore
        self, name: str, value: Any, attrs: Optional[Dict[str, Any]] = None, renderer: Optional['BaseRenderer'] = None
    ) -> str:
        if attrs is None:
            attrs = {}
        attrs['compressed_value'] = value
        return super().render(name, value, attrs=attrs, renderer=renderer)

    def decompress(self, value: Any) -> Tuple[Any, Any]:  # type: ignore
        if isinstance(value, (tuple, list)):
            return value[0], value[1]
        if value:
            ct = ContentType.objects.get_for_model(value)
            return force_str(ct.pk), value
        return None, None

    class Media:
        js = (
            # https://docs.djangoproject.com/en/3.2/ref/contrib/admin/#contrib-admin-jquery
            'admin/js/jquery.init.js',
            'admin/js/generic_foreign_key_field_widget.js',
        )


class FilterableSelect(forms.Select):
    template_name = 'forms/widgets/filterable_select.html'
    option_template_name = "forms/widgets/filterable_select_option.html"


class CheckboxSelectMultipleMulticolumn(forms.CheckboxSelectMultiple):
    template_name = 'forms/widgets/checkbox_select_multiple_multicolumn.html'

    def __init__(self, *args, columns: int = 3, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs['columns'] = columns


class LivePreviewWidget(forms.Textarea):
    template_name = 'forms/widgets/live_preview_widget.html'

    PREVIEW_MODE = 'preview'
    CODE_MODE = 'code'
    preview_modes = (CODE_MODE, PREVIEW_MODE)

    def __init__(self, *args, default_preview_mode: str = CODE_MODE, **kwargs):
        if default_preview_mode not in self.preview_modes:
            raise ValueError(f'Invalid preview mode: {default_preview_mode}')
        self.default_preview_mode = default_preview_mode
        super().__init__(*args, **kwargs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['default_preview_mode'] = self.default_preview_mode
        return context

    class Media:
        css = {'all': ('css/preview_widget.css',)}
        js = ['js/preview_widget.js']

