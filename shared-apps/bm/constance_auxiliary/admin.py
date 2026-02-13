import hashlib
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, cast

from bm.constance_auxiliary import local_settings
from constance import config
from constance import settings as constance_settings  # type: ignore
from constance.admin import FIELDS, ConstanceAdmin, ConstanceForm, get_values
from django import VERSION, forms  # type: ignore
from django.apps import apps
from django.contrib import admin, messages
from django.contrib.admin.options import csrf_protect_m
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.core.handlers.wsgi import WSGIRequest
from django.db.models import Model
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.encoding import smart_bytes
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.apps import AppConfig
    from django.http import HttpRequest, HttpResponse


class CustomConfigForm(ConstanceForm):
    def clean(self) -> None:
        for name in constance_settings.CONFIG:
            validator_path = local_settings.FIELD_VALIDATORS.get(name)
            if validator_path is not None:
                validator = import_string(validator_path)
                try:
                    validator(self.cleaned_data[name])
                except Exception as e:
                    self.add_error(name, f'{e.__class__}: {e}')


class SingleFieldConstanceForm(forms.Form):
    version = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, initial: Dict[str, Any], name: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, initial=initial, **kwargs)  # type: ignore[misc]
        version_hash = hashlib.md5()
        options = constance_settings.CONFIG[name]
        default, help_text = options[0], options[1]
        if len(options) == 3:
            config_type = options[2]
            if config_type not in constance_settings.ADDITIONAL_FIELDS and not isinstance(
                options[0], config_type
            ):
                raise ImproperlyConfigured(
                    _(
                        "Default value type must be "
                        "equal to declared config "
                        "parameter type. Please fix "
                        "the default value of "
                        "'%(name)s'."
                    )
                    % {'name': name}
                )
        else:
            config_type = type(default)

        if config_type not in FIELDS:
            raise ImproperlyConfigured(
                _(
                    "Constance doesn't support "
                    "config values of the type "
                    "%(config_type)s. Please fix "
                    "the value of '%(name)s'."
                )
                % {'config_type': config_type, 'name': name}
            )
        field_class, kwargs = FIELDS[config_type]
        self.fields[name] = field_class(label=name, **kwargs)

        version_hash.update(smart_bytes(initial.get(name, '')))
        self.initial['version'] = version_hash.hexdigest()
        self.name = name

    def save(self) -> None:
        if getattr(config, self.name) != self.cleaned_data[self.name]:
            setattr(config, self.name, self.cleaned_data[self.name])

    def clean_version(self) -> None:
        value = self.cleaned_data['version']

        if constance_settings.IGNORE_ADMIN_VERSION_CHECK:
            return value

        if value != self.initial['version']:
            raise forms.ValidationError(
                _(
                    'The settings have been modified '
                    'by someone else. Please reload the '
                    'form and resubmit your changes.'
                )
            )
        return value

    def clean(self) -> None:  # type: ignore[override]
        validator_path = local_settings.FIELD_VALIDATORS.get(self.name)
        if validator_path is not None:
            validator = import_string(validator_path)
            try:
                validator(self.cleaned_data[self.name])
            except Exception as e:
                self.add_error(self.name, f'{e.__class__}: {e}')


class SingleFieldConstanceAdmin(ConstanceAdmin):
    change_list_form = SingleFieldConstanceForm

    @csrf_protect_m
    def changelist_view(
        self, request: 'HttpRequest', extra_context: Optional[Dict[str, Any]] = None
    ) -> 'HttpResponse':
        if not self.has_change_permission(request, None):
            raise PermissionDenied
        initial = get_values()
        form_cls = self.get_changelist_form(request)
        name = self.model._meta.field_name
        form = form_cls(initial=initial, name=name)
        if request.method == 'POST':
            form = form_cls(data=request.POST, initial=initial, name=name)
            if form.is_valid():
                form.save()
                messages.add_message(
                    request,
                    messages.SUCCESS,
                    _('Live settings updated successfully.'),
                )
                return HttpResponseRedirect('.')
        context = dict(
            admin.site.each_context(cast(WSGIRequest, request)),
            config_values=[],
            title=self.model._meta.app_config.verbose_name,
            app_label='constance',
            opts=self.model._meta,
            form=form,
            media=self.media + form.media,
            icon_type='gif' if VERSION < (1, 9) else 'svg',
        )
        options = constance_settings.CONFIG[name]
        context['config_values'].append(self.get_config_value(name, options, form, initial))
        request.current_app = self.admin_site.name  # type: ignore[attr-defined]
        return TemplateResponse(request, self.change_list_template, context)


for name in local_settings.FIELDS_WITH_OWN_CHANGE_PERMISSION:

    class SingleFieldConstanceModelSubstitution:
        class Meta:
            app_label = 'constance_auxiliary'
            object_name = name
            model_name = module_name = name
            field_name = name
            verbose_name_plural = ' '.join(name.capitalize().split('_'))
            abstract = False
            swapped = False

            def get_ordered_objects(self) -> bool:
                return False

            def get_change_permission(self) -> str:
                return f'change_{name}'

            @property
            def app_config(self) -> 'AppConfig':
                return apps.get_app_config(self.app_label)

        _meta = Meta()

    admin.site.register([cast(Type[Model], SingleFieldConstanceModelSubstitution)], SingleFieldConstanceAdmin)
