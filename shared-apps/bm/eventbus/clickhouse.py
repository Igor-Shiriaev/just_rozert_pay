import json
from typing import Optional, Any, Final
from uuid import UUID

from bm.eventbus.events import Event, EVENT_PAYLOAD_BY_EVENT_TYPE, UserEventPayload
from bm.eventbus.serialization import make_event_from_data
from bm.utils import instance_as_data, json_dumps
from bm.clickhouse import ClickHouseRepo


class EventbusEventsClickHouseRepo(ClickHouseRepo[Event]):
    DB_NAME: Final = 'eventslog'
    TABLE_NAME: Final = 'events'
    ZEROES_UUID: Final = UUID('00000000-0000-0000-0000-000000000000')
    COLUMNS: Final = ['event_type', 'uuid', 'user_uuid', 'payload', 'created_at']

    @classmethod
    def decode_record(cls, row: tuple) -> Event:
        data = dict(zip(cls.COLUMNS, row))
        data['event_id'] = data.pop('uuid')
        data['payload'] = json.loads(data['payload'])
        return make_event_from_data(data)

    @classmethod
    def encode_record(cls, record: Event) -> dict:
        payload_dict = instance_as_data(record.payload)
        if isinstance(record.payload, UserEventPayload):
            user_uuid = record.payload.user_id
            # Leave 'user_id' field in payload_dict as is, even though we extract it to 
            # root field as well. It allows to preserve original event payload format
            # in order to process (read) it later with the same UserEventPayload model.
        else:
            # From ClickHouse docs:
            # "You can use Nullable-typed expressions in the PRIMARY KEY and ORDER BY clauses but
            # it is strongly discouraged."
            # Since user_uuid is part of Primary Key we add zero-based UUID in case it's non-user event.
            user_uuid = cls.ZEROES_UUID

        return {
            'event_type': record.event_type.value,
            'uuid': record.event_id,
            'user_uuid': user_uuid,
            'payload': json_dumps(payload_dict),
            'created_at': record.created_at,
        }

    @classmethod
    def make_repo(cls, host: str, port: int, user: str, password: str) -> 'EventbusEventsClickHouseRepo':
        return cls(
            host=host,
            port=port,
            user=user,
            password=password,
            table_qualname=f'{cls.DB_NAME}.{cls.TABLE_NAME}',
            decode_record=cls.decode_record,
            encode_record=cls.encode_record,
            columns=cls.COLUMNS,
            use_real_count=True,
        )

    def filter(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None,
        **filter_params: Any,
    ) -> list[Event]:
        if 'event_type' in filter_params:
            payload_class = EVENT_PAYLOAD_BY_EVENT_TYPE[filter_params['event_type']]
            if not issubclass(payload_class, UserEventPayload):
                # All non-user events are bound to special (fake) zeroes-uuid user.
                # From ClickHouse docs:
                # "You can use Nullable-typed expressions in the PRIMARY KEY and ORDER BY clauses but
                # it is strongly discouraged."
                # Since user_uuid is part of Primary Key we add zero-based UUID in case it's non-user event.
                filter_params['user_uuid'] = self.ZEROES_UUID

        return super().filter(limit=limit, offset=offset, order_by=order_by, **filter_params)

    def configure_clickhouse_ddl(self) -> None:
        self.client.execute(f'CREATE DATABASE IF NOT EXISTS {self.DB_NAME}')
        self.client.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_qualname}
            (
                event_type String,
                uuid UUID,
                user_uuid UUID COMMENT '00000000-0000-0000-0000-000000000000 in case it"s non-user event',
                payload String COMMENT 'most often it"s json string',
                created_at DateTime64(6, 'UTC') COMMENT 'event generation time'
            )
            ENGINE = MergeTree()
            PARTITION BY toYYYYMM(created_at)
            PRIMARY KEY (user_uuid, created_at)
            """
        )
