import datetime
import logging
from typing import (
    TYPE_CHECKING, Any, Dict, Iterable, Optional, Tuple,
    Type, Union,
)

from django.contrib.admin.options import InlineModelAdmin, BaseModelAdmin
from django.core.exceptions import FieldDoesNotExist
from django.db.models import ForeignKey
from django.template import loader
from django.utils.html import format_html
from django.utils.safestring import mark_safe, SafeText, SafeString
from django.utils.timezone import localtime

from admin_customize.const import get_bool_icon
from admin_customize.fields import GenericForeignKeyField
from admin_customize.widgets import GenericForeignKeyRawIdWidget
from bm.utils import format_datetime

if TYPE_CHECKING:
    from django.db.models import Model
    from django.forms import ModelForm
    from django.http import HttpRequest
    from admin_customize.admin import BaseTabularInline

logger = logging.getLogger(__name__)

Fieldset = Tuple[Optional[str], Dict[str, Iterable[str]]]
Inline = Type[InlineModelAdmin]
FieldsetOrInline = Union[Fieldset, Inline]


class GenericForeignKeyFormMixin:
    modeladmin: Optional['GenericForeignKeyMixin'] = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # type: ignore
        obj = kwargs.get('instance')
        initial = kwargs.get('initial', {})
        if obj:
            assert self.modeladmin is not None
            for name in self.modeladmin.generic_raw_id_fields:
                initial[name] = getattr(obj, name)
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)  # type: ignore


class GenericForeignKeyMixin:
    generic_raw_id_fields: Iterable[str] = ()

    def generic_modelform_factory(self, form: Type['ModelForm']) -> Type['ModelForm']:
        """
        The modeform_factory skips generic fields, so we start with a new form
        that has our generic fields already declared.
        """
        class_name = self.model.__name__ + 'Form'  # type: ignore
        bases = (GenericForeignKeyFormMixin, form)

        attrs = {
            'modeladmin': self,
        }

        for name in self.generic_raw_id_fields:
            db_field = getattr(self.model, name)  # type: ignore
            opts = db_field.model._meta
            ct_field = opts.get_field(db_field.ct_field)
            fk_field = opts.get_field(db_field.fk_field)
            required = not ct_field.blank or not fk_field.blank
            attrs[name] = GenericForeignKeyField(db_field, required=required)

        return type(form)(class_name, bases, attrs)  # type: ignore

    def get_form(  # type: ignore
        self, request: 'HttpRequest', obj: Optional['Model'] = None, **kwargs: Any
    ) -> Type['ModelForm']:
        form = kwargs.get('form', self.form)  # type: ignore
        kwargs['form'] = self.generic_modelform_factory(form)  # type: ignore
        form = super().get_form(request, obj, **kwargs)  # type: ignore
        for name in self.generic_raw_id_fields:
            db_field = getattr(self.model, name)  # type: ignore
            form.base_fields[name].widget = GenericForeignKeyRawIdWidget(db_field, self.admin_site)  # type: ignore
            form.base_fields[name].help_text = (
                'Select a type, then click the search icon to select the ' 'related object.'
            )
        return form

    def save_model(self, request: 'HttpRequest', obj: 'Model', form: 'ModelForm', change: bool) -> None:
        for name in self.generic_raw_id_fields:
            value = form.cleaned_data.get(name, getattr(obj, name))
            setattr(obj, name, value)
        super().save_model(request, obj, form, change)  # type: ignore

    def to_field_allowed(self, request: 'HttpRequest', to_field: str) -> bool:
        # This method causes an exception in ModelAdmin since it calls
        # get_related_field() on GenericRel. This extra check is not really
        # necessary unless you're doing something strange.
        return True


def wrap_field(method) -> Any:
    def wrap(*args, **kwargs) -> Any:
        data = method(*args, **kwargs)
        if isinstance(data, datetime.datetime):
            return format_datetime(data)
        if data is None:
            return '-'
        if isinstance(data, bool):
            if data:
                return mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
            else:
                return mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')
        return data

    return wrap


class InlineAsFieldAdminMixin:
    def render_inline(self, inline: Type['BaseTabularInline'], obj: 'Model', with_link: bool = False) -> Optional[str]:
        if not inline.readonly_fields == inline.fields:
            raise RuntimeError(
                'render_inline can be used only with inlines without '
                'editable fields, {inline} has editable fields'.format(inline=inline.__name__)
            )
        if not obj.pk:
            return '-'
        related_model = inline.model
        relation_field_name = self._get_fk_field_name(related_model, type(obj))
        related_objects = related_model.objects.filter(**{relation_field_name: obj})
        if inline.ordering:
            related_objects = related_objects.order_by(*inline.ordering)
        if not related_objects:
            return '-'
        if with_link:
            header_link = ['']
        else:
            header_link = []
        render_context = {
            'name': inline.__name__,
            'header': header_link + [self._get_field_verbose_name(f, inline) for f in inline.fields],
            'rows': [self._make_table_row(obj, inline, with_link=with_link) for obj in related_objects],
        }
        template = loader.get_template('admin/includes/inline_as_field.html')
        return template.render(render_context)

    def _make_table_row(self, obj: 'Model', inline: Type['BaseTabularInline'], *, with_link: bool) -> list[Any]:
        from common.admin_utils import get_admin_url  # TODO: it's BM deps

        if with_link:
            view_link = get_admin_url(self.admin_site, obj=obj)  # type: ignore[attr-defined]
            view_col = [mark_safe(f'<a href="{view_link}"><span class="viewlink">VIEW</a>')]
        else:
            view_col = []

        return view_col + [self._get_field_value(f, obj, inline) for f in inline.fields]

    def _get_fk_field_name(self, model: Type['Model'], related_model: Type['Model']) -> str:
        for field in model._meta.get_fields():
            if isinstance(field, ForeignKey) and field.related_model == related_model:
                return field.name
        raise ValueError("No foreign key field found for {} in {}".format(related_model, model))

    def _get_field_verbose_name(self, field_name: str, inline: Type['BaseTabularInline']) -> str:
        try:
            field = inline.model._meta.get_field(field_name)
            return field.verbose_name or field_name.capitalize().replace('_', ' ')
        except FieldDoesNotExist:
            pass
        attr = getattr(inline.model, field_name, None) or getattr(inline, field_name, None)
        if not attr:
            raise ValueError("Field {} not found in {} nor {}".format(field_name, inline.model, inline))
        return (
            attr.short_description if hasattr(attr, 'short_description') else field_name.capitalize().replace('_', ' ')
        )

    @wrap_field
    def _get_field_value(self, field_name: str, obj: 'Model', inline: Type['BaseTabularInline']) -> Any:
        val = getattr(obj, field_name, None)
        if val is not None:
            if not callable(val):
                if isinstance(val, datetime.datetime):
                    return localtime(val)
                return val
            if callable(val):
                return val(obj)
        attr = getattr(inline, field_name, None)
        if attr and callable(attr):
            return attr(self, obj)
        return None


class DictAsTableReprMixin:
    @mark_safe
    def render_dict_as_table(
        self,
        data: dict[str, Any],
        name: Optional[str] = None,
        base_header_col: Optional[str] = None,
        header_row: Optional[Iterable[str]] = None,
        flat: bool = False,
        full_width: bool = True,
    ) -> str:
        """
        Dict should have same keys on second level
        """
        if not data:
            return '-'
        header_row = header_row or data.keys()
        template = loader.get_template('admin/dict_as_table.html')
        return template.render(
            {
                'name': name,
                'context': data,
                'base_header_col': base_header_col or '',
                'header_row': header_row,
                'flat': flat,
                'full_width': full_width,
            }
        )

    def prepare_values_to_render(
        self,
        data: dict[str, Any],
    ) -> dict[str, Union[str, SafeString]]:
        prepared_values = {}

        for key, value in data.items():
            if isinstance(value, bool):
                prepared_values[key] = get_bool_icon(value)
            elif isinstance(value, (list, tuple, set)):
                prepared_values[key] = ', '.join(value)
            elif isinstance(value, datetime.datetime):
                prepared_values[key] = value.isoformat(timespec='seconds')
            else:
                prepared_values[key] = value

        return prepared_values


class RelatedLinksMixin(BaseModelAdmin):
    def get_related_link(self, obj: 'Model', field_name: str) -> SafeText:
        related_object = getattr(obj, field_name, None)
        if related_object is None:
            return SafeText('-')
        related_object_name = type(related_object).__name__.lower()
        related_object_app = type(related_object)._meta.app_label
        related_object_url = self.reverse_admin_url(
            f'{related_object_app}_{related_object_name}_change',
            kwargs={'object_id': related_object.id},
        )
        return format_html('<a href="{}">{}</a>', related_object_url, str(related_object))
