import logging
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence, Union, cast
from uuid import UUID

from django.conf import settings
from django.contrib import admin
from django.forms import Media
from django.http import HttpRequest
from django.utils.safestring import SafeText, mark_safe

from admin_customize.filters import InputFilter, MultipleChoiceFilter, PresetsFilter
from bm.eventbus.clickhouse import EventbusEventsClickHouseRepo
from bm.eventbus.constants import OBSOLETE_EVENT_TYPES, EventType
from bm.eventbus.events import EVENT_TYPES_BY_GROUP, Event, EventGroup
from .entities_admin import EntityAdmin, EntityFakeModel, EntityFakeModelManager
from .eventbus_admin_presenter import ListViewPayload, presenters_registry

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


class EventbusEventTypeFilter(MultipleChoiceFilter):
    title = 'Event Type'
    parameter_name = 'event_type'
    event_types: list[EventType] = list(EventType)

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin) -> list:
        # e.g. ('DEPOSIT_INIT', 'Deposit init')
        return [
            (
                t,
                ' '.join([s.lower() for s in t.split('_')]).capitalize()
            )
            for t in self.event_types if t not in OBSOLETE_EVENT_TYPES
        ]

    def queryset(self, request: HttpRequest, queryset: 'QuerySet') -> Optional['QuerySet']:
        value = self.value()
        if value:
            return queryset.filter(event_type__in=value)
        return None


class EventbusEventGroupFilter(PresetsFilter):
    title = 'Event Group'
    parameter_name = 'event_type'

    _ALL_EXCEPT_SYSTEM_GROUP = '_ALL_EXCEPT_SYSTEM_GROUP'

    def lookups(
            self, request: HttpRequest, model_admin: admin.ModelAdmin
    ) -> list[tuple[str, str]]:
        # e.g. ('USER_PROFILE', 'User Profile')
        options: list[tuple[str, str]] = [
            (cast(str, group.value), ' '.join([s.lower() for s in group.split('_')]).capitalize())
            for group in sorted(EVENT_TYPES_BY_GROUP)
        ]
        options.append((self._ALL_EXCEPT_SYSTEM_GROUP, 'All Except System'))
        return options

    def get_preset_by_value(self, value: str) -> list[str]:
        if value == self._ALL_EXCEPT_SYSTEM_GROUP:
            _params = [group for group in EVENT_TYPES_BY_GROUP if group != EventGroup.SYSTEM]
            return [cast(str, t.value) for group in _params for t in EVENT_TYPES_BY_GROUP[group]]
        else:
            return list(map(lambda x: x.value, EVENT_TYPES_BY_GROUP.get(EventGroup(value), [])))


class EventbusEventUserUUIDFilter(InputFilter):
    title = 'User UUID'
    parameter_name = 'user_uuid'

    def queryset(self, request: HttpRequest, queryset: 'QuerySet') -> Optional['QuerySet']:
        value = self.value()
        if not value:
            return None

        try:
            uuid_value = UUID(value)
            return queryset.filter(user_uuid=uuid_value)
        except ValueError:
            return None


class EventbusEventFakeModelManager(EntityFakeModelManager):
    _limit: Optional[int] = None
    _offset: Optional[int] = None
    _cached_items: Optional[list['EventbusEventFakeModel']] = None
    _cached_count: Optional[int] = None

    repo = EventbusEventsClickHouseRepo.make_repo(
        host=settings.CLICKHOUSE_HOST,  # type: ignore
        port=settings.CLICKHOUSE_HTTP_PORT,  # type: ignore
        user=settings.CLICKHOUSE_USER,  # type: ignore
        password=settings.CLICKHOUSE_PASSWORD,  # type: ignore
    )

    def get_by_pk(self, pk: str) -> EntityFakeModel:
        user_uuid, event_uuid = Event.parse_pk(pk)
        instance = self.eventbus_events_repo.get(user_uuid=user_uuid, uuid=event_uuid)
        return EventbusEventFakeModel(instance)

    def _fetch_all(self) -> list['EventbusEventFakeModel']:
        if self._cached_items is not None:
            return self._cached_items
        items = self.eventbus_events_repo.filter(
            offset=self._offset, limit=self._limit, **self._filter_params,
            order_by='-created_at',
        )
        self._cached_items = [EventbusEventFakeModel(item) for item in items]
        return self._cached_items

    def __iter__(self) -> Iterable[EntityFakeModel]:
        items = self._fetch_all()
        return iter(items)

    def __len__(self) -> int:
        if self._cached_count is None:
            self._cached_count = self.eventbus_events_repo.count(**self._filter_params)
        return self._cached_count

    def __getitem__(
            self, key: Union[int, slice]
    ) -> Union['EntityFakeModel', list['EntityFakeModel']]:
        if isinstance(key, slice):
            self._offset = key.start
            self._limit = key.stop - key.start
            return list(self)  # type: ignore
        self._limit = key
        self._offset = key
        return list(self)[key]  # type: ignore

    @property
    def eventbus_events_repo(self) -> EventbusEventsClickHouseRepo:
        return self.repo


class EventbusEventFakeModel(EntityFakeModel):
    class Meta:
        entity = Event
        app_label = 'betmaster'
        model_name = 'eventbusevent'
        verbose_name = 'Eventbus event'
        verbose_name_plural = 'Eventbus events'
        manager_class = EventbusEventFakeModelManager

    def __str__(self) -> str:
        return f'{self.instance.event_type} {self.instance.event_id}'


class EventbusEventAdmin(EntityAdmin):
    list_display = (
        'created_at_formatted',
        'event_type',
        'payload_listview',
        'event_id',
        'related_entity_link',
        'user_link',
    )
    readonly_fields = (
        'event_id',
        'event_type',
        'payload_full',
        'created_at',
        'user_link',
        'related_entity_link',
    )
    list_display_links = ('created_at_formatted',)
    list_filter = (
        EventbusEventGroupFilter,
        EventbusEventTypeFilter,
        EventbusEventUserUUIDFilter,
        'created_at',
    )

    list_per_page = 200

    @property
    def media(self) -> Media:
        media = Media(
            js=['js/block_visibility_toggle.js'],
            css={'screen': ['css/custom-admin-styles.css', ]},
        )
        return super().media + media

    @mark_safe
    def created_at_formatted(self, obj: Event) -> str:
        return obj.created_at.strftime('%d.%m.%Y&nbsp;%H:%M:%S')

    created_at_formatted.short_description = 'Created at'  # type: ignore

    def get_list_display(self, request: 'HttpRequest') -> Sequence[str]:
        list_display = super().get_list_display(request)
        if request.GET.get('show_id', None):
            return list_display
        return [field for field in list_display if field != 'event_id']

    def get_readonly_fields(self, request: 'HttpRequest', obj: Any = None) -> list[str]:
        return list(self.readonly_fields)

    @mark_safe
    def user_link(self, obj: Event) -> SafeText:
        if hasattr(obj.payload, 'user_id'):
            user_id = getattr(obj.payload, 'user_id')
            link_url = self.reverse_admin_url(f'betmaster_user_changelist') + f'?q={user_id}'
            return SafeText(f'<a href="{link_url}">user link</a>')
        return SafeText('-')

    user_link.short_description = 'User Link'  # type: ignore

    @mark_safe
    def related_entity_link(self, obj: EventbusEventFakeModel) -> str:
        if obj.event_type == EventType.USER_REGISTRATION_STATUS_CHANGED:
            return self.user_link(obj)  # type: ignore[arg-type]

        return presenters_registry.get_event_related_entity_link_presenter(
            obj.instance
        ).related_entity_link()

    related_entity_link.short_description = 'Related Entity'  # type: ignore

    @mark_safe
    def payload_listview(self, obj: EventbusEventFakeModel) -> Union[dict, str]:
        return ListViewPayload.from_payload(obj.instance).render_list()

    payload_listview.short_description = 'Payload'  # type: ignore

    @mark_safe
    def payload_full(self, obj: EventbusEventFakeModel) -> str:
        data = ListViewPayload.from_payload(obj.instance).render_detailed()
        return f'<pre>{data}</pre>'

    payload_full.short_description = 'Payload'  # type: ignore
