from abc import abstractmethod
from typing import TYPE_CHECKING, Iterable, List, Optional, cast

from django.conf import settings
from django.contrib import messages
from django.db.models import Model, QuerySet
from django.utils.safestring import SafeString

from admin_customize.admin import BaseModelAdmin
from admin_customize.admin.utils import log_change, log_change_bulk
from admin_customize.const import get_bool_icon
from admin_customize.decorators import (
    cast_to_admin_action,
    cast_to_admin_field,
    cast_to_list_admin_action,
)
from admin_customize.images_management.init import get_s3

if TYPE_CHECKING:
    from django.http import HttpRequest


class EnablingModel(Model):
    is_enabled: bool

    class Meta:
        abstract = True


class EnablingError(Exception):
    pass


class EnableValidationError(EnablingError):
    pass


class DisableValidationError(EnablingError):
    pass


class EnabledMixin(BaseModelAdmin):
    readonly_fields: Iterable[str] = ('field_is_enabled',)
    change_actions: Iterable[str] = (
        'action_enable',
        'action_disable',
    )
    actions: Iterable[str] = (
        'list_action_enable',
        'list_action_disable',
    )
    ENABLED_SHOULD_BE_LOCKED = False

    def get_change_actions(
        self, request: 'HttpRequest', object_id: Optional[int], form_url: str
    ) -> Iterable[str]:
        actions = cast(List[str], super().get_change_actions(request, object_id, form_url))  # type: ignore
        actions_to_remove = []
        if object_id is None:
            actions_to_remove.append('action_enable')
            actions_to_remove.append('action_disable')
            return [action for action in actions if action not in actions_to_remove]
        obj = cast(EnablingModel, self.get_object(request, object_id))  # type: ignore
        if self.ENABLED_SHOULD_BE_LOCKED and obj.is_enabled:
            return ['action_disable']
        if obj and obj.is_enabled:
            actions_to_remove.append('action_enable')
        elif obj and not obj.is_enabled:
            actions_to_remove.append('action_disable')
        return [action for action in actions if action not in actions_to_remove]

    def _action_enable(self, request: 'HttpRequest', obj: EnablingModel) -> None:
        if obj.is_enabled:
            self.message_user(request, 'Already enabled', messages.INFO)
            return
        try:
            self.validate_before_enable(obj)
        except EnableValidationError as e:
            self.message_user(request, str(e), messages.ERROR)  # type: ignore
            return
        else:
            obj.is_enabled = True
            obj.save()
            self.message_user(request, f'Enabled {obj}', messages.SUCCESS)  # type: ignore
            log_change(request.user.id, cast('Model', obj), 'Enabled')

    @cast_to_admin_action
    def action_enable(self, request: 'HttpRequest', obj: EnablingModel) -> None:
        self._action_enable(request, obj)
    action_enable.label = 'Enable'

    def _list_action_enable_logic(
        self, request: 'HttpRequest', queryset: QuerySet[EnablingModel]
    ) -> None:
        invalid_for_enable_objects: list[tuple[EnablingModel, Exception]] = []
        for obj in queryset:
            try:
                self.validate_before_enable(obj)
            except EnableValidationError as e:
                invalid_for_enable_objects.append((obj, e))
        if invalid_for_enable_objects:
            error_message = f'''The request can not be performed.\n
            Some objects cannot be enabled:\n
            {invalid_for_enable_objects}'''
            self.message_user(request, error_message, messages.ERROR)  # type: ignore
            return
        else:
            queryset.update(is_enabled=True)
            self.message_user(request, f'Enabled {queryset.count()} objects', messages.SUCCESS)
            log_change_bulk(request.user.id, queryset, 'Enabled with bulk action')

    @cast_to_list_admin_action
    def list_action_enable(
        self, request: 'HttpRequest', queryset: QuerySet[EnablingModel]
    ) -> None:
        self._list_action_enable_logic(request, queryset)
    list_action_enable.label = 'Enable'
    list_action_enable.short_description = 'Enable'

    def _action_disable(self, request: 'HttpRequest', obj: EnablingModel) -> None:
        if not obj.is_enabled:
            self.message_user(request, 'Already disabled', messages.INFO)
            return
        try:
            self.validate_before_disable(obj)
        except DisableValidationError as e:
            self.message_user(request, str(e), messages.ERROR)  # type: ignore
            return
        else:
            obj.is_enabled = False
            obj.save()
            self.message_user(request, f'Disabled {obj}', messages.SUCCESS)  # type: ignore
            log_change(request.user.id, cast('Model', obj), 'Disabled')

    @cast_to_admin_action
    def action_disable(self, request: 'HttpRequest', obj: EnablingModel) -> None:
        self._action_disable(request, obj)
    action_disable.label = 'Disable'

    def _list_action_disable(
        self, request: 'HttpRequest', queryset: QuerySet[EnablingModel]
    ) -> None:
        invalid_for_disable_objects: list[tuple[EnablingModel, Exception]] = []
        for obj in queryset:
            try:
                self.validate_before_disable(obj)
            except DisableValidationError as e:
                invalid_for_disable_objects.append((obj, e))
        if invalid_for_disable_objects:
            error_message = f'''The request can not be performed.\n
            Some objects cannot be disabled:\n
            {invalid_for_disable_objects}'''
            self.message_user(request, error_message, messages.ERROR)
            return
        else:
            queryset.update(is_enabled=False)
            self.message_user(request, f'Disabled {queryset.count()} objects', messages.SUCCESS)
            log_change_bulk(request.user.id, queryset, 'Disabled with bulk action')

    @cast_to_list_admin_action
    def list_action_disable(
        self, request: 'HttpRequest', queryset: QuerySet[EnablingModel]
    ) -> None:
        self._list_action_disable(request, queryset)
    list_action_disable.label = 'Disable'
    list_action_disable.short_description = 'Disable'

    @cast_to_admin_field
    def field_is_enabled(self, obj: EnablingModel) -> SafeString:
        return get_bool_icon(obj.is_enabled)

    field_is_enabled.short_description = 'Enabled'
    field_is_enabled.inline_actions = [
        'action_enable',
        'action_disable',
    ]

    @abstractmethod
    def validate_before_enable(self, obj: Model) -> None:
        """
        Should raise EnableValidationError if obj cannot be enabled
        """

    @abstractmethod
    def validate_before_disable(self, obj: Model) -> None:
        """
        Should raise DisableValidationError if obj cannot be disabled
        """


def validate_all_images_uploaded_to_s3(urls: List[Optional[str]]) -> None:
    """
    Validate that all images are uploaded to s3 and have proxy url
    """
    try:
        env_configurations = settings.CURRENT_ENV_CONFIGURATION_FACTORY()
    except ImportError:
        return

    if not env_configurations.features_availability.require_images_on_our_s3:
        return

    s3_url = get_s3().public_url_for_public_static_bucket
    if any([(url and not url.startswith(s3_url)) for url in urls]):
        raise EnableValidationError('Not all images are uploaded to our s3')
