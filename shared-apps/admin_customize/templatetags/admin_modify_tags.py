import datetime
from functools import partial
from typing import Any, Dict, Optional, Type, Union

import ujson
from django import template
from django.contrib.admin.helpers import AdminReadonlyField
from django.contrib.admin.templatetags.admin_modify import submit_row as original_submit_row
from django.contrib.admin.utils import lookup_field
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.db import models
from django.db.models import JSONField
from django.forms import Form
from django.template.context import Context
from django.template.context import RequestContext  # type: ignore[attr-defined]
from django.template.exceptions import TemplateSyntaxError  # type: ignore[attr-defined]
from django.template.loader import get_template
from django.urls import reverse
from django.utils.safestring import SafeText, mark_safe

from bm.utils import log_errors

register = template.Library()


@register.inclusion_tag('admin/submit_line.html', takes_context=True)
def submit_row(context: RequestContext) -> Context:  # type: ignore
    ctx = original_submit_row(context)
    ctx.update(
        {
            'show_save': context.get('show_save', ctx['show_save']),
            'show_save_and_add_another': context.get(
                'show_save_and_add_another', ctx['show_save_and_add_another']
            ),
            'show_save_and_continue': context.get(
                'show_save_and_continue', ctx['show_save_and_continue']
            ),
            'show_delete_link': context.get('show_delete_link', ctx['show_delete_link']),
        }
    )
    return ctx


@register.simple_tag
def is_json_field(field: AdminReadonlyField) -> bool:  # type: ignore
    json_readonly_fields = getattr(field.model_admin, 'json_readonly_fields', None)
    if json_readonly_fields is not None and field.field['name'] in json_readonly_fields:
        return True
    try:
        model_field = field.model_admin.model._meta.get_field(field.field['name'])
        if type(model_field) == JSONField:
            return True
    except (AttributeError, FieldDoesNotExist):
        return False
    return False


@register.simple_tag
def prepare_json_for_readonly_layout(field: AdminReadonlyField) -> str:  # type: ignore
    field_data = field.field['field']
    obj = field.form.instance
    model_admin = field.model_admin
    try:
        f, attr, value = lookup_field(field_data, obj, model_admin)
        return ujson.dumps(value)
    except (AttributeError, ValueError, ObjectDoesNotExist):
        pass
    return field.contents()


@register.filter
def dict_as_json(data: dict[str, Any], wrapper_name: Optional[str] = None) -> str:  # type: ignore
    if wrapper_name:
        return ujson.dumps({wrapper_name: data})
    return ujson.dumps(data)


@register.inclusion_tag('admin/includes/readonly_json_field.html', takes_context=True)
def readonly_json_field(context: dict[str, Any]) -> dict[str, Any]:  # type: ignore
    return context


@register.simple_tag
def get_data_by_name(data: Union[Form, dict], field_name: str) -> Any:  # type: ignore
    return data[field_name]


@register.simple_tag
def get_data_by_name_safe(data: Union[Form, dict], field_name: str) -> Any:  # type: ignore
    if isinstance(data, dict):
        return data.get(field_name)
    return getattr(data, field_name, None)


@register.filter
def dict_key(d: Dict[str, Any], key: str) -> Any:  # type: ignore
    return d.get(key)


@register.filter
@mark_safe
def show_empty_if_none(value: Optional[str]) -> str:  # type: ignore
    if value is None:
        return '<span style="color: red"><b>EMPTY</b></span>'
    else:
        return value


@register.simple_tag
@mark_safe
@log_errors
def build_admin_link(obj: Union[models.Model, Type[models.Model]], href: bool = True) -> str:
    if isinstance(obj, models.Model):
        model: Type[models.Model] = obj.__class__
        link = reverse(
            f'admin:{model._meta.app_label}_{model._meta.model_name}_change',
            args=[obj.pk],
        )
    elif issubclass(obj, models.Model):
        model = obj
        link = reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_changelist')
    else:
        raise RuntimeError

    if href:
        return f'<a href="{link}" target="_blank">{str(obj)}</a>'
    return link


@register.filter
def verbose_dict(data_to_render: Union[dict, str], intend: bool = False) -> str:
    component_template = get_template('admin/includes/verbose_dict.html')
    if isinstance(data_to_render, str):
        return data_to_render
    lines = []
    for key, value in data_to_render.items():
        name = key.capitalize().split('_')
        inner_intend_func = partial(verbose_dict, intend=True)
        if isinstance(value, int) and value > 1_000_000_000_000:
            value = datetime.datetime.fromtimestamp(value / 1000)
        if isinstance(value, datetime.datetime):
            value = value.strftime('%d-%m-%Y %H:%M:%S')
        if isinstance(value, bool):
            value = 'Yes' if value else 'No'
        if isinstance(value, list):
            if all(isinstance(item, dict) for item in value):
                value = '\n'.join(inner_intend_func(item) for item in value)
            else:
                value = '\n'.join(str(item) for item in value)
        if isinstance(value, dict):
            value = inner_intend_func(value)
        if not isinstance(value, str):
            value = str(value)
        value = SafeText(value)
        lines.append({'name': ' '.join(name), 'value': value})
    return component_template.render({'data': lines, 'intend': intend})


@register.filter
def formatted_date(value: Optional[Union[datetime.datetime, datetime.date]]) -> Optional[SafeText]:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return SafeText(value.strftime('%d.%m.%Y&nbsp;%H:%M:%S'))
    elif isinstance(value, datetime.date):
        return SafeText(value.strftime('%d.%m.%Y'))
    raise TemplateSyntaxError('Invalid date type: %s' % type(value))
