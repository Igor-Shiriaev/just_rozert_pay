from typing import TYPE_CHECKING, Any, Optional

from django import forms
from django.utils.safestring import SafeString
from django.contrib.contenttypes.models import ContentType

if TYPE_CHECKING:
    from django.contrib.contenttypes.fields import GenericForeignKey


class GenericForeignKeyField(forms.MultiValueField):
    def __init__(self, gfk_field: 'GenericForeignKey', *args: Any, **kwargs: Any) -> None:  # type: ignore
        self.gfk_field = gfk_field
        opts = gfk_field.model._meta  # noqa
        ct_field = opts.get_field(gfk_field.ct_field)
        fk_field = opts.get_field(gfk_field.fk_field)
        fields = (ct_field.formfield(), fk_field.formfield())
        super().__init__(fields=fields, *args, **kwargs)

    def compress(self, data: Any) -> Any:  # type: ignore
        if not data:
            return None
        ct, pk = data
        return ct.get_object_for_this_type(pk=pk)

    def prepare_value(self, data: Any) -> Any:  # type: ignore
        if isinstance(data, (list, tuple)):
            if not all(data):
                return None
            ct_pk, obj_pk = data
            ct = ContentType.objects.get(pk=ct_pk)
            obj = ct.get_object_for_this_type(pk=obj_pk)
            return obj
        return data


class ExtendedHelpFieldMixin:
    def __init__(self, *args, extended_help: Optional[SafeString] = None, **kwargs):
        self.extended_help = extended_help
        super().__init__(*args, **kwargs)


class ExtendedJSONField(ExtendedHelpFieldMixin, forms.JSONField):
    pass
