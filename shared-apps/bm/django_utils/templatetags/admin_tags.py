import json

from typing import Dict

from django.template import Library
from django.contrib.admin.utils import lookup_field
from django.contrib.admin.helpers import AdminReadonlyField
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist

try:
    from django.db.models import JSONField
except ImportError:
    from django.contrib.postgres.fields import JSONField  # type: ignore

register = Library()


@register.simple_tag
def is_json_field(field: AdminReadonlyField) -> bool:   # type: ignore
    try:
        model_field = field.model_admin.model._meta.get_field(
            field.field['name']
        )
        if isinstance(model_field, JSONField):
            return True
    except (AttributeError, FieldDoesNotExist):
        return False
    return False


@register.simple_tag
def prepare_json_for_readonly_layout(field: AdminReadonlyField) -> str:     # type: ignore
    field_data = field.field['field']
    obj = field.form.instance
    model_admin = field.model_admin
    try:
        f, attr, value = lookup_field(field_data, obj, model_admin)
        return json.dumps(value)
    except (AttributeError, ValueError, ObjectDoesNotExist):
        pass
    return field.contents()


@register.inclusion_tag('admin/includes/readonly_json_field.html', takes_context=True)
def readonly_json_field(context: Dict) -> Dict:         # type: ignore
    return context
