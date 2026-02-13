from typing import (TYPE_CHECKING, Any, ClassVar, Dict, List, Optional,
                    Sequence, Tuple, Type, Union, cast)

from django.db.models import Model
from django.db.models.query import QuerySet
from django.http import HttpRequest
from pydantic import BaseModel, Field, root_validator

if TYPE_CHECKING:
    from admin_customize.admin import BaseModelAdmin
    from b2b_admin.admin import B2BAdminDashboardStatus
    from common.configurations.entities import B2BAdminConfiguration
    from django.contrib.admin import AdminSite
    from django.contrib.auth.models import User


class ContentFiltrationPath(BaseModel):
    user_relation_path: str
    user_related_lookup_path: ClassVar[str]
    permission_type: ClassVar[str]
    marker_all: ClassVar[str]
    b2b_admin_config_key: ClassVar[str]

    def get_user_allowed_params(self, user: 'User') -> Sequence[str]:
        if user.is_superuser:
            return [
                self.marker_all,
            ]
        permissions = user.get_all_permissions()
        full_permission_prefix = self.make_full_permission_prefix()
        if f'{full_permission_prefix}_{self.marker_all}' in permissions:
            return [
                self.marker_all,
            ]
        return [
            p.split(f'{full_permission_prefix}_')[1]
            for p in permissions
            if p.startswith(full_permission_prefix)
        ]

    @classmethod
    def make_full_permission_prefix(cls) -> str:
        return f'betmaster.admincontentfiltration_user_{cls.permission_type}'

    @classmethod
    def make_permission(cls, option: str) -> str:
        return f'{cls.make_full_permission_prefix().split(".")[1]}_{option}'

    def get_admin_allowed_params(
        self, admin_site: Union['AdminSite', 'B2BAdminDashboardStatus']
    ) -> Sequence[str]:
        configuration = self.__get_admin_site_configuration(admin_site)
        if configuration is None:
            return [self.marker_all]
        entity_filter = getattr(configuration.allowed_entities_filters, self.b2b_admin_config_key)
        if entity_filter == '<ALL>':  # common.configurations.entities.ALL_PLACEHOLDER
            return [self.marker_all]
        return entity_filter

    def __get_admin_site_configuration(
        self, admin_site: Union['AdminSite', 'B2BAdminDashboardStatus']
    ) -> Optional['B2BAdminConfiguration']:
        if hasattr(admin_site, 'configuration'):
            return cast('B2BAdminConfiguration', admin_site.configuration)  # type: ignore
        return None

    def filter_queryset(
        self,
        queryset: QuerySet,
        user: 'User',
        admin_site: Union['AdminSite', 'B2BAdminDashboardStatus'],
    ) -> QuerySet:
        admin_based_params = self.get_admin_allowed_params(admin_site)
        user_based_params = self.get_user_allowed_params(user)
        queryset = self._filter_queryset(queryset, admin_based_params)
        queryset = self._filter_queryset(queryset, user_based_params)
        return queryset

    def _filter_queryset(self, queryset: QuerySet, allowed_params: Sequence[str]) -> QuerySet:
        if self.marker_all in allowed_params:
            return queryset
        if not allowed_params:
            return queryset.none()
        return queryset.filter(**{self._make_lookup_path(): allowed_params})

    def _make_lookup_path(self) -> str:
        if self.user_relation_path:
            return f'{self.user_relation_path}__{self.user_related_lookup_path}__in'
        return f'{self.user_related_lookup_path}__in'

    @classmethod
    def make_permissions(cls, options: List[str]) -> List[Tuple[str, str]]:
        """
        Generate permissions with all available options.
        Should be used in permissions declaration in models.
        """
        raise NotImplementedError()


class MarketContentFiltrationPath(ContentFiltrationPath):
    user_related_lookup_path: ClassVar[str] = 'extra__market'

    permission_type: ClassVar[str] = 'market'
    marker_all: ClassVar[str] = 'markets_all'
    b2b_admin_config_key: ClassVar[str] = 'product_markets'

    @classmethod
    def make_permissions(cls, options: List[str]) -> List[Tuple[str, str]]:
        return [
            (cls.make_permission(cls.marker_all), 'Can view content for all markets (custom)'),
            *[
                (cls.make_permission(marker), f'Can view content for market "{marker}" (custom)')
                for marker in options
            ],
        ]


class DomainGroupContentFiltrationPath(ContentFiltrationPath):
    user_related_lookup_path: ClassVar[str] = 'extra__domain_group'

    permission_type: ClassVar[str] = 'domain_group'
    marker_all: ClassVar[str] = 'domain_groups_all'
    b2b_admin_config_key: ClassVar[str] = 'domain_groups'

    @classmethod
    def make_permissions(cls, options: List[str]) -> List[Tuple[str, str]]:
        return [
            (
                cls.make_permission(cls.marker_all),
                'Can view content for all domain groups (custom)',
            ),
            *[
                (
                    cls.make_permission(marker),
                    f'Can view content for domain group "{marker}" (custom)',
                )
                for marker in options
            ],
        ]


class BrandContentFiltrationPath(ContentFiltrationPath):
    user_related_lookup_path: ClassVar[str] = 'brand'

    permission_type: ClassVar[str] = 'brand'
    marker_all: ClassVar[str] = 'brands_all'
    b2b_admin_config_key: ClassVar[str] = 'brands'

    @classmethod
    def make_permissions(cls, options: List[str]) -> List[Tuple[str, str]]:
        return [
            (
                cls.make_permission(cls.marker_all),
                'Can view content for all brands (custom)',
            ),
            *[
                (
                    cls.make_permission(marker),
                    f'Can view content for brand "{marker}" (custom)',
                )
                for marker in options
            ],
        ]


class LicenseContentFiltrationPath(ContentFiltrationPath):
    user_related_lookup_path: ClassVar[str] = 'extra__license'

    permission_type: ClassVar[str] = 'license'
    marker_all: ClassVar[str] = 'licenses_all'
    b2b_admin_config_key: ClassVar[str] = 'licenses'

    @classmethod
    def make_permissions(cls, options: List[str]) -> List[Tuple[str, str]]:
        return [
            (
                cls.make_permission(cls.marker_all),
                'Can view content for all licenses (custom)',
            ),
            *[
                (
                    cls.make_permission(marker),
                    f'Can view content for license "{marker}" (custom)',
                )
                for marker in options
            ],
        ]


class IndirectFilteringConfig(BaseModel):
    get_parameter_name: str
    model_path: str
    entity_attribute_name: str = Field(
        ..., description='Attribute name in Object, in case if not equals to get_parameter_name'
    )

    def get_model_class(self) -> Type[Model]:
        return self._get_model_class(self.model_path)

    @root_validator(pre=True)
    def validate_model_path(cls, values: Dict[str, Any]) -> dict:
        model_path = values.get('model_path')
        if not model_path:
            raise ValueError('model_path should be defined')
        try:
            cls._get_model_class(model_path)
        except LookupError:
            raise ValueError(f'Model "{model_path}" not found')
        return values

    @staticmethod
    def _get_model_class(model_path: str) -> Type[Model]:
        from django.apps import apps

        model_class = apps.get_model(model_path)
        return cast(Type[Model], model_class)


class ContentFiltrationConfig(BaseModel):
    """
    Configuration for content filtration.
    Should be defined as queryset filter.
    """

    user_relation_path: Optional[str] = Field(
        default=None,
        description='Should be defined if Model has db relation to User',
    )
    indirect_model_config: Optional[IndirectFilteringConfig] = Field(
        default=None,
        description='Should be defined if Admin has no DB relation to User (e.g. Clickhouse archive model)',
    )

    _filters: ClassVar[List[Type[ContentFiltrationPath]]] = [
        MarketContentFiltrationPath,
        DomainGroupContentFiltrationPath,
        BrandContentFiltrationPath,
        LicenseContentFiltrationPath,
    ]
    filters: List[ContentFiltrationPath]

    @root_validator(pre=True)
    def validate_user_relation_path(cls, values: Dict[str, Any]) -> dict:
        user_relation_path = values.get('user_relation_path')
        indirect_model_config = values.get('indirect_model_config')
        if user_relation_path is None and indirect_model_config is None:
            raise ValueError(
                'Either user_relation_path or user_id_get_parameter should be defined'
            )
        if user_relation_path is not None and indirect_model_config is not None:
            raise ValueError(
                'Only one of user_relation_path or indirect_model_config should be defined'
            )
        return values

    @root_validator(pre=True)
    def fill_filters(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        user_relation_path = values.get('user_relation_path', '')
        filters = [
            filter_cls(user_relation_path=user_relation_path) for filter_cls in cls._filters
        ]
        values['filters'] = filters
        return values

    def filter_queryset(
        self,
        queryset: QuerySet,
        user: 'User',
        admin_site: Union['AdminSite', 'B2BAdminDashboardStatus'],
    ) -> QuerySet:
        for filtration_path in self.filters:
            queryset = filtration_path.filter_queryset(queryset, user, admin_site)
        return queryset


class ContentFiltrationMeta(type):
    def __new__(meta, name: str, bases, classdict) -> Any:  # type: ignore
        if not meta._is_CONTENT_FILTRATION_defined(bases, classdict):
            return super(ContentFiltrationMeta, meta).__new__(meta, name, bases, classdict)

        CONTENT_FILTRATION = meta._get_CONTENT_FILTRATION(bases, classdict)
        # if None do not change behaviour, otherwise add filtration mixin
        if CONTENT_FILTRATION is not None:
            already_inherited = False
            for cls in bases:
                if ContentFiltrationMixin in cls.mro():
                    already_inherited = True
                    break
            if not already_inherited:
                bases = (ContentFiltrationMixin,) + bases

        class_ = cast(
            Type[ContentFiltrationMixin],
            cast(object, super(ContentFiltrationMeta, meta).__new__(meta, name, bases, classdict)),
        )
        if hasattr(class_, 'CONTENT_FILTRATION') and isinstance(class_.CONTENT_FILTRATION, dict):
            class_.CONTENT_FILTRATION = ContentFiltrationConfig.parse_obj(
                class_.CONTENT_FILTRATION
            )
        return class_

    @staticmethod
    def _get_CONTENT_FILTRATION(
        bases: Sequence[Type['BaseModelAdmin']], classdict: dict
    ) -> Optional[ContentFiltrationConfig]:  # type: ignore
        if 'CONTENT_FILTRATION' in classdict:
            return classdict['CONTENT_FILTRATION']
        for cls in bases:
            if 'CONTENT_FILTRATION' in cls.__dict__:
                return cls.__dict__['CONTENT_FILTRATION']
        return None

    @staticmethod
    def _is_CONTENT_FILTRATION_defined(
        bases: Sequence[Type['BaseModelAdmin']], classdict: dict
    ) -> bool:  # type: ignore
        if 'CONTENT_FILTRATION' in classdict:
            return True
        for cls in bases:
            if 'CONTENT_FILTRATION' in cls.__dict__:
                return True
        return False


class ContentFiltrationMixin:
    CONTENT_FILTRATION: Optional[Union[ContentFiltrationConfig, dict]]

    admin_site: Union['AdminSite', 'B2BAdminDashboardStatus']

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Used in list view"""
        queryset = super().get_queryset(request)  # type: ignore[misc]
        if not self.__has_content_filtration_config():
            return queryset
        content_filtration_config = self.__get_content_filtration_config()
        if content_filtration_config.user_relation_path is not None:
            return self._filter_queryset_by_user_relation_path(
                content_filtration_config, queryset, request
            )
        elif content_filtration_config.indirect_model_config is not None:
            return self._filter_queryset_by_parameter(
                content_filtration_config,
                queryset,
                request,
            )
        else:
            raise RuntimeError('CONTENT_FILTRATION is not properly configured')

    def get_object(
        self, request: HttpRequest, object_id: str, from_field: Optional[str] = None
    ) -> Optional[Model]:
        """Used in obj view, if we have indirect content filtration"""
        obj = super().get_object(request, object_id, from_field)  # type: ignore[misc]
        if obj is None:
            return None
        if not self.__has_content_filtration_config():
            return obj
        content_filtration_config = self.__get_content_filtration_config()
        if content_filtration_config.user_relation_path is not None:
            return obj
        elif content_filtration_config.indirect_model_config is not None:
            if self._is_object_accessible_by_parameter(content_filtration_config, obj, request):
                return obj
            return None
        else:
            raise RuntimeError('CONTENT_FILTRATION is not properly configured')

    def _filter_queryset_by_user_relation_path(
        self, content_filtration, queryset: QuerySet, request: HttpRequest
    ) -> QuerySet:
        return content_filtration.filter_queryset(queryset, request.user, self.admin_site)  # type: ignore

    def _is_object_accessible_by_parameter(
        self, content_filtration, obj: Model, request: HttpRequest
    ) -> bool:
        """Check if currently opened object is related to entity allowed for user"""
        model_config = content_filtration.indirect_model_config

        if not hasattr(obj, model_config.entity_attribute_name):
            raise RuntimeError(f'Object has no attribute {model_config.entity_attribute_name}')

        entity_attr_value = getattr(obj, model_config.entity_attribute_name)

        checking_queryset = model_config.get_model_class().objects.filter(pk=entity_attr_value)
        checking_queryset = content_filtration.filter_queryset(
            checking_queryset, request.user, self.admin_site
        )
        return checking_queryset.exists()

    def _filter_queryset_by_parameter(
        self, content_filtration, queryset: QuerySet, request: HttpRequest
    ) -> QuerySet:
        """Filter queryset by entity passed as GET parameter, see WalletTransactionArchivedAdmin for example"""
        model_config = content_filtration.indirect_model_config

        get_parameter = request.GET.get(model_config.get_parameter_name)
        if get_parameter is None:
            return queryset.filter(**{model_config.get_parameter_name: 0})

        checking_queryset = model_config.get_model_class().objects.filter(pk=get_parameter)
        checking_queryset = content_filtration.filter_queryset(
            checking_queryset, request.user, self.admin_site
        )
        if not checking_queryset.exists():
            return queryset.filter(**{model_config.get_parameter_name: 0})

        return queryset

    def __has_content_filtration_config(self) -> bool:
        return hasattr(self, 'CONTENT_FILTRATION') and self.CONTENT_FILTRATION is not None

    def __get_content_filtration_config(self) -> ContentFiltrationConfig:
        if not self.__has_content_filtration_config():
            raise RuntimeError('CONTENT_FILTRATION is not defined')
        if isinstance(self.CONTENT_FILTRATION, dict):
            return ContentFiltrationConfig.parse_obj(self.CONTENT_FILTRATION)
        elif isinstance(self.CONTENT_FILTRATION, ContentFiltrationConfig):
            return self.CONTENT_FILTRATION
        else:
            raise ValueError('CONTENT_FILTRATION should be dict or ContentFiltrationConfig')
