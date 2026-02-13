import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, Iterable, Optional, Type, TypeVar, Union, cast

from admin_customize.admin import BaseModelAdmin
from django.apps import apps
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models.base import ModelBase
from django.forms.models import modelform_factory
from django.forms.utils import pretty_name
from django.http import HttpRequest, HttpResponse

if TYPE_CHECKING:
    from django.db.models import QuerySet


logger = logging.getLogger(__name__)


class EntityFakeModelField:
    is_relation = False
    auto_created = False
    remote_field = None
    choices = None
    encoder = DjangoJSONEncoder

    field_mapping = {
        datetime: models.DateTimeField,
        bool: models.BooleanField,
        dict: models.JSONField,
    }

    @property  # type: ignore[misc]
    def __class__(self) -> type:
        if self.plain_type in self.field_mapping:
            return self.field_mapping[self.plain_type]
        return EntityFakeModelField

    def __init__(self, name: str, plain_type: Any):
        self.name = name
        self.verbose_name = pretty_name(name)
        self.plain_type = plain_type

    def __eq__(self, other: 'EntityFakeModelField') -> bool:  # type: ignore
        if isinstance(other, EntityFakeModelField):
            return self.name == other.name
        return NotImplemented  # type: ignore

    def __lt__(self, other: 'EntityFakeModelField') -> bool:
        if isinstance(other, EntityFakeModelField):
            return self.name < other.name
        return NotImplemented  # type: ignore


class EntityFakeModelBase(ModelBase):
    def __new__(mcs, name, bases, attrs, **kwargs):  # type: ignore
        parents = [b for b in bases if isinstance(b, ModelBase)]
        if not parents:
            return type.__new__(mcs, name, bases, attrs)

        attr_meta = attrs.pop('Meta')
        _validate_meta(attr_meta)

        attrs['manager_class'] = attr_meta.manager_class

        new_class = type.__new__(mcs, name, bases, attrs)
        new_class._meta = EntityFakeModelOptions(attr_meta)
        return new_class

    def __getattr__(self, key: str) -> Any:
        if key == '__dataclass_fields__':
            return None
        try:
            return self._meta.get_field(key)
        except KeyError:
            return super().__getattribute__(key)


def _validate_meta(meta: Any) -> None:
    required_attrs = [
        'entity',
        'app_label',
        'model_name',
        'verbose_name',
        'verbose_name_plural',
        'manager_class',
    ]
    for required_attr in required_attrs:
        if not hasattr(meta, required_attr):
            raise AttributeError(f'"{required_attr}" is required field')


class EntityFakeModelOptions:
    app_label: str
    model_name: str
    verbose_name: str
    verbose_name_plural: str
    object_name: str

    abstract: bool = False
    swapped: bool = False
    private_fields: list = []
    many_to_many: list = []
    related_fkey_lookups: list = []

    entity: Any

    class pk:
        attname = 'pk'

    def __init__(self, meta: Any):
        self.entity = meta.entity
        self.app_label = meta.app_label
        self.model_name = meta.model_name
        self.verbose_name = meta.verbose_name
        self.verbose_name_plural = meta.verbose_name_plural
        self.object_name = meta.model_name

        self._fields = OrderedDict(
            [
                (f.name, EntityFakeModelField(f.name, f.type_))
                for f in self.entity.__fields__.values()
            ]
        )

    @property
    def app_config(self):  # type: ignore
        return apps.app_configs.get(self.app_label)

    @property
    def concrete_fields(self) -> list[EntityFakeModelField]:
        return list(self._fields.values())

    def get_field(self, name: str) -> EntityFakeModelField:
        if name not in self._fields:
            raise FieldDoesNotExist(name)
        return self._fields[name]


class EntityFakeModel(metaclass=EntityFakeModelBase):
    manager_class: Type['EntityFakeModelManager']

    def __init__(self, instance: Any):
        self.instance = instance

    def __getattr__(self, key: str) -> Any:
        if hasattr(self.instance, key):
            return getattr(self.instance, key)
        return super().__getattribute__(key)

    def serializable_value(self, attr: str) -> Any:
        return getattr(self.instance, attr)


T_Model = TypeVar('T_Model', bound=EntityFakeModel)


class EntityFakeModelManager(ABC, Generic[T_Model]):
    def __init__(self) -> None:
        self._filter_params: dict[str, Any] = {}

    @abstractmethod
    def get_by_pk(self, pk: str) -> T_Model:
        pass

    def filter(self, **filter_params: Any) -> 'EntityFakeModelManager':
        self._filter_params.update(filter_params)
        return self

    @abstractmethod
    def __iter__(self) -> Iterable[T_Model]:
        pass

    @abstractmethod
    def __len__(self) -> int:
        pass

    @abstractmethod
    def __getitem__(self, key: Union[int, slice]) -> Union[T_Model, list[T_Model]]:
        pass

    def count(self) -> int:
        return len(self)

    def _clone(self) -> 'EntityFakeModelManager':
        return self


class EntityFakeModelChangeList(ChangeList):
    def get_queryset(self, request):  # type: ignore
        (
            self.filter_specs,
            self.has_filters,
            remaining_lookup_params,
            filters_use_distinct,
            _,
        ) = self.get_filters(request)

        qs = self.root_queryset
        for filter_spec in self.filter_specs:
            new_qs = filter_spec.queryset(request, qs)
            if new_qs is not None:
                qs = new_qs

        return qs

    def get_ordering(self, request, queryset):  # type: ignore
        return []

    def get_ordering_field_columns(self):  # type: ignore
        return {}


class EntityAdmin(BaseModelAdmin):
    actions = None  # if the value is None the actions select doesn't show

    def get_queryset(self, request: 'HttpRequest') -> 'QuerySet':
        return self.model.manager_class()

    def get_changelist(
        self, request: 'HttpRequest', **kwargs: Any
    ) -> Type['EntityFakeModelChangeList']:
        return EntityFakeModelChangeList

    def get_fieldsets(
        self, request: 'HttpRequest', obj: Optional['EntityFakeModel'] = None
    ) -> list:
        return [(None, {'fields': self.get_readonly_fields(request, obj)})]

    def get_readonly_fields(  # type: ignore[override]
        self, request: 'HttpRequest', obj: Optional['EntityFakeModel'] = None  # type: ignore[override]
    ) -> list[str]:
        readonly_fields: list[str] = []
        for field in self.model._meta.concrete_fields:
            if field.name not in (self.exclude or []):
                readonly_fields.append(field.name)

        for field_name in self.readonly_fields:
            if field_name not in readonly_fields:
                readonly_fields.append(str(field_name))

        return cast(list[str], readonly_fields)

    def changeform_view(
        self,
        request: 'HttpRequest',
        object_id: str = None,
        form_url: str = '',
        extra_context: Any = None,
    ) -> HttpResponse:
        assert object_id is not None  # mypy
        obj = self.get_object(request, object_id)
        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, self.model._meta, object_id)
        Form = modelform_factory(self.model, fields=())
        admin_form = admin.helpers.AdminForm(
            form=Form(instance=cast(Optional[models.Model], obj)),
            fieldsets=list(self.get_fieldsets(request, obj)),
            prepopulated_fields={},
            readonly_fields=self.get_readonly_fields(request, obj),
            model_admin=self,
        )
        context = {
            **self.admin_site.each_context(request),  # type: ignore
            'title': f'View {self.model._meta.verbose_name}',
            'adminform': admin_form,
            'object_id': object_id,
            'original': obj,
            'is_popup': False,
            'to_field': None,
            'media': self.media,
            'inline_admin_formsets': [],
            # 'errors': helpers.AdminErrorList(form, formsets),
            'preserved_filters': self.get_preserved_filters(request),
        }
        return self.render_change_form(
            request, context, add=False, change=True, obj=obj, form_url=form_url
        )

    def get_object(
        self, request: 'HttpRequest', object_id: Optional[Any], from_field: str = None
    ) -> Optional['EntityFakeModel']:
        try:
            return self.model.manager_class().get_by_pk(object_id)
        except ObjectDoesNotExist:
            return None

    def has_add_permission(self, request: 'HttpRequest') -> bool:
        return False

    def has_delete_permission(self, request: 'HttpRequest', obj: 'EntityFakeModel' = None) -> bool:
        return False

    def has_change_permission(self, request: 'HttpRequest', obj: 'EntityFakeModel' = None) -> bool:
        return False
